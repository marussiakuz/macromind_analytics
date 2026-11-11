"""Rule-based red flags over extracted facts and slide text.

A flag is a prompt for the analyst to check something, not a finding about the company.
Thresholds are expert starting points and live in FlagConfig so they can be reviewed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from osint_agent.pitchdeck.models import (
    DeckFact,
    FactStatus,
    FlagKind,
    Metric,
    RedFlag,
    Severity,
    Slide,
)
from osint_agent.pitchdeck.normalize import same_amount, year_ranges, years_in_text

_NO_COMPETITORS = re.compile(
    r"(?:нет|отсутствуют|не имеет|не имеют|без)\s+(?:прямых\s+|полных\s+|российских\s+)?(?:конкурент\w*|аналог\w*)"
    r"|аналог\w*\s+(?:нет|отсутствуют)|конкурент\w*\s+(?:нет|отсутствуют)",
    re.I,
)
_SUPERLATIVE = re.compile(
    r"единственн\w+\s+(?:в\s+(?:мире|росси\w+|стране)|на\s+рынке)|миров\w+\s+лидер|лучш\w+\s+в\s+мире"
    r"|уникальн\w+\s+в\s+мире|абсолютн\w+\s+лидер|монополист\w*",
    re.I,
)
_SOURCE = re.compile(r"источник|по\s+данным|source|данные\s+\w+|\bRPI\b|исследовани", re.I)
_FINANCE_WORDS = re.compile(r"выручк|ebitda|прибыл|финанс", re.I)
_PART_OF_YEAR = re.compile(r"квартал|полугод|месяц|\bQ[1-4]\b|\b[1-4]\s*кв\b", re.I)

_SECTIONS = {
    "команда": re.compile(r"команд|основател|founder|team|генеральн\w+ директор|CEO", re.I),
    "рынок": re.compile(r"рын[о,к]|TAM|SAM|SOM|market", re.I),
    "конкуренты": re.compile(r"конкурент|аналог|competitor", re.I),
    "финансы": re.compile(r"выручк|ebitda|финанс|доход|revenue", re.I),
    "запрос инвестиций": re.compile(r"инвестиц|раунд|привлеч|финансировани|investment", re.I),
}


@dataclass(frozen=True)
class FlagConfig:
    hockey_cagr_medium: float = 1.0
    hockey_cagr_high: float = 2.0
    hockey_min_years: int = 3
    plan_fact_ratio: float = 0.7
    inconsistency_tolerance: float = 0.05
    market_share_ambitious: float = 25.0
    customer_concentration: float = 50.0
    ebitda_margin_extreme: float = 0.5
    stale_years: int = 2
    review_threshold_share: float = 0.5


def _money(fact: DeckFact) -> bool:
    return fact.unit_kind in {"RUB", "USD", "EUR"} and fact.amount is not None


def _single_year(fact: DeckFact) -> int | None:
    return fact.years[0] if len(fact.years) == 1 else None


def _by_metric(facts: list[DeckFact], metric: Metric) -> list[DeckFact]:
    return [f for f in facts if f.metric == metric and f.amount is not None]


def _no_entity(fact: DeckFact) -> bool:
    return not fact.entity


def _partial_year(fact: DeckFact) -> bool:
    """A quarter or a part of a year cannot be compared with a full-year number."""
    return bool(_PART_OF_YEAR.search(f"{fact.period_raw} {fact.label} {fact.quote}"))


def _fmt_rub(fact: DeckFact) -> str:
    return f"{fact.value_raw} {fact.unit_raw}".strip()


def rule_hockey_stick(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    series = [f for f in _by_metric(facts, Metric.revenue) if _money(f) and _single_year(f) and _no_entity(f)]
    series = [f for f in series if (f.amount or 0) > 0]
    if len(series) < 2:
        return []
    by_year: dict[int, DeckFact] = {}
    for fact in series:
        year = _single_year(fact)
        if year not in by_year or fact.status == FactStatus.forecast:
            by_year[year] = fact
    facts_only = [f for f in by_year.values() if f.status == FactStatus.fact]
    forecast = [f for f in by_year.values() if f.status == FactStatus.forecast]
    if not forecast:
        return []
    last = max(forecast, key=_single_year)
    base_pool = facts_only or forecast
    base = max(base_pool, key=_single_year) if facts_only else min(base_pool, key=_single_year)
    years = _single_year(last) - _single_year(base)
    if years < cfg.hockey_min_years or base.unit_kind != last.unit_kind:
        return []
    cagr = (last.amount / base.amount) ** (1 / years) - 1
    if cagr < cfg.hockey_cagr_medium:
        return []
    severity = Severity.high if cagr >= cfg.hockey_cagr_high else Severity.medium
    return [RedFlag(
        rule="hockey_stick",
        severity=severity,
        kind=FlagKind.numeric,
        title="Очень резкий рост выручки в прогнозе",
        detail=(
            f"От {_fmt_rub(base)} ({_single_year(base)}) до {_fmt_rub(last)} ({_single_year(last)}): "
            f"около {cagr * 100:.0f}% в год. Проверьте, на чём основан прогноз."
        ),
        slides=sorted({base.slide, last.slide}),
        fact_ids=[base.id, last.id],
    )]


def rule_forecast_without_fact(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    revenue = _by_metric(facts, Metric.revenue)
    forecast = [f for f in revenue if f.status == FactStatus.forecast]
    if not forecast or any(f.status == FactStatus.fact for f in revenue):
        return []
    return [RedFlag(
        rule="forecast_without_fact",
        severity=Severity.medium,
        kind=FlagKind.numeric,
        title="Есть прогноз выручки, но нет достигнутой выручки",
        detail="В деке выручка показана только как план. Запросите фактическую отчётность.",
        slides=sorted({f.slide for f in forecast}),
        fact_ids=[f.id for f in forecast],
    )]


def rule_plan_fact_gap(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    flags = []
    for metric in (Metric.revenue, Metric.ebitda, Metric.net_profit):
        items = [
            f for f in _by_metric(facts, metric)
            if _money(f) and _single_year(f) and _no_entity(f) and not _partial_year(f)
        ]
        for fact in (f for f in items if f.status == FactStatus.fact):
            plans = [
                p for p in items
                if p.status == FactStatus.forecast
                and _single_year(p) == _single_year(fact)
                and p.unit_kind == fact.unit_kind
            ]
            for plan in plans:
                if plan.amount > 0 and fact.amount < cfg.plan_fact_ratio * plan.amount:
                    flags.append(RedFlag(
                        rule="plan_fact_gap",
                        # The status comes from the model and is its weakest field.
                        severity=Severity.medium,
                        kind=FlagKind.numeric,
                        title="Факт заметно ниже плана",
                        detail=(
                            f"{plan.label or metric.value} за {_single_year(fact)}: "
                            f"план {_fmt_rub(plan)}, факт {_fmt_rub(fact)}."
                        ),
                        slides=sorted({fact.slide, plan.slide}),
                        fact_ids=[fact.id, plan.id],
                    ))
    return flags


def rule_inconsistent_values(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    groups: dict[tuple, list[DeckFact]] = {}
    for fact in facts:
        if fact.amount is None or not fact.years or fact.entity or fact.status == FactStatus.unknown:
            continue
        if _partial_year(fact):
            continue
        if fact.metric in {Metric.growth_rate, Metric.customer_share, Metric.other}:
            continue
        key = (fact.metric, tuple(fact.years), fact.status, fact.unit_kind)
        groups.setdefault(key, []).append(fact)
    flags = []
    for (metric, years, _, _), items in groups.items():
        slides = {f.slide for f in items}
        if len(slides) < 2:
            continue
        low = min(items, key=lambda f: f.amount)
        high = max(items, key=lambda f: f.amount)
        if high.amount and (high.amount - low.amount) / abs(high.amount) > cfg.inconsistency_tolerance:
            flags.append(RedFlag(
                rule="inconsistent_values",
                severity=Severity.high,
                kind=FlagKind.numeric,
                title="Разные значения одного показателя на разных слайдах",
                detail=(
                    f"{low.label or metric.value}, период {years[0]}"
                    f"{'–' + str(years[-1]) if len(years) > 1 else ''}: "
                    f"{_fmt_rub(low)} (слайд {low.slide}) и {_fmt_rub(high)} (слайд {high.slide})."
                ),
                slides=sorted({low.slide, high.slide}),
                fact_ids=[low.id, high.id],
            ))
    return flags


def rule_market_funnel(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    def pick(metric: Metric) -> DeckFact | None:
        items = [f for f in _by_metric(facts, metric) if _money(f)]
        return max(items, key=lambda f: f.amount) if items else None

    tam, sam, som = pick(Metric.market_tam), pick(Metric.market_sam), pick(Metric.market_som)
    flags = []
    for wide, narrow, names in ((tam, sam, "TAM и SAM"), (sam, som, "SAM и SOM"), (tam, som, "TAM и SOM")):
        if wide and narrow and wide.unit_kind == narrow.unit_kind and narrow.amount > wide.amount:
            flags.append(RedFlag(
                rule="market_funnel_order",
                severity=Severity.high,
                kind=FlagKind.numeric,
                title=f"Нарушен порядок оценок рынка: {names}",
                detail=f"Более узкая оценка ({_fmt_rub(narrow)}) больше широкой ({_fmt_rub(wide)}).",
                slides=sorted({wide.slide, narrow.slide}),
                fact_ids=[wide.id, narrow.id],
            ))
    return flags


def rule_market_without_source(facts: list[DeckFact], slides: list[Slide], cfg: FlagConfig) -> list[RedFlag]:
    market = {Metric.market_tam, Metric.market_sam, Metric.market_som, Metric.market_size}
    text_by_slide = {s.number: s.text for s in slides}
    unsourced = sorted({
        f.slide for f in facts
        if f.metric in market
        and text_by_slide.get(f.slide, "").strip()
        and not _SOURCE.search(text_by_slide.get(f.slide, ""))
    })
    if not unsourced:
        return []
    return [RedFlag(
        rule="market_without_source",
        severity=Severity.medium,
        kind=FlagKind.claim,
        title="Оценка рынка без указанного источника",
        detail="На слайде с объёмом рынка в тексте нет ссылки на источник. Источник на картинке текстовая проверка не видит.",
        slides=unsourced,
    )]


def rule_ambitious_share(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    items = [
        f for f in _by_metric(facts, Metric.market_share)
        if f.unit_kind == "percent" and f.status != FactStatus.fact and f.amount >= cfg.market_share_ambitious
    ]
    if not items:
        return []
    top = max(items, key=lambda f: f.amount)
    return [RedFlag(
        rule="ambitious_market_share",
        severity=Severity.medium,
        kind=FlagKind.numeric,
        title="Амбициозная целевая доля рынка",
        detail=f"Заявлена доля {_fmt_rub(top)}{' к ' + top.period_raw if top.period_raw else ''}. Проверьте, как она получена.",
        slides=[top.slide],
        fact_ids=[top.id],
    )]


def rule_revenue_vs_market(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    revenue = [f for f in _by_metric(facts, Metric.revenue) if _money(f) and _no_entity(f)]
    if not revenue:
        return []
    top = max(revenue, key=lambda f: f.amount)
    flags = []
    for metric, name, severity in (
        (Metric.market_som, "SOM", Severity.medium),
        (Metric.market_sam, "SAM", Severity.high),
        (Metric.market_tam, "TAM", Severity.high),
    ):
        items = [f for f in _by_metric(facts, metric) if _money(f) and f.unit_kind == top.unit_kind]
        if items:
            market = max(items, key=lambda f: f.amount)
            if top.amount > market.amount:
                flags.append(RedFlag(
                    rule="revenue_exceeds_market",
                    severity=severity,
                    kind=FlagKind.numeric,
                    title=f"Выручка больше заявленного {name}",
                    detail=f"Выручка {_fmt_rub(top)} при {name} {_fmt_rub(market)}.",
                    slides=sorted({top.slide, market.slide}),
                    fact_ids=[top.id, market.id],
                ))
    return flags


def rule_margins(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    revenue = {
        _single_year(f): f for f in _by_metric(facts, Metric.revenue)
        if _money(f) and _single_year(f) and _no_entity(f) and f.amount > 0
    }
    ebitda = {
        _single_year(f): f for f in _by_metric(facts, Metric.ebitda)
        if _money(f) and _single_year(f) and _no_entity(f)
    }
    net = {
        _single_year(f): f for f in _by_metric(facts, Metric.net_profit)
        if _money(f) and _single_year(f) and _no_entity(f)
    }
    flags = []
    extreme = [y for y in ebitda if y in revenue and ebitda[y].amount / revenue[y].amount >= cfg.ebitda_margin_extreme]
    if extreme:
        year = max(extreme)
        margin = ebitda[year].amount / revenue[year].amount
        flags.append(RedFlag(
            rule="extreme_margin",
            severity=Severity.medium,
            kind=FlagKind.numeric,
            title="Очень высокая рентабельность",
            detail=f"EBITDA составляет около {margin * 100:.0f}% выручки за {year} год.",
            slides=sorted({ebitda[year].slide, revenue[year].slide}),
            fact_ids=[ebitda[year].id, revenue[year].id],
        ))
    for year in sorted(set(net) & set(ebitda)):
        if net[year].amount > ebitda[year].amount > 0:
            flags.append(RedFlag(
                rule="net_above_ebitda",
                severity=Severity.high,
                kind=FlagKind.numeric,
                title="Чистая прибыль выше EBITDA",
                detail=f"За {year} год: чистая прибыль {_fmt_rub(net[year])}, EBITDA {_fmt_rub(ebitda[year])}.",
                slides=sorted({net[year].slide, ebitda[year].slide}),
                fact_ids=[net[year].id, ebitda[year].id],
            ))
    return flags


def rule_customer_concentration(facts: list[DeckFact], cfg: FlagConfig) -> list[RedFlag]:
    items = [
        f for f in _by_metric(facts, Metric.customer_share)
        if f.unit_kind == "percent" and f.amount >= cfg.customer_concentration
    ]
    if not items:
        return []
    top = max(items, key=lambda f: f.amount)
    who = f" ({top.entity})" if top.entity else ""
    return [RedFlag(
        rule="customer_concentration",
        severity=Severity.medium,
        kind=FlagKind.numeric,
        title="Зависимость от одного клиента",
        detail=f"На одного клиента{who} приходится {_fmt_rub(top)}.",
        slides=[top.slide],
        fact_ids=[top.id],
    )]


def rule_stale_plans(facts: list[DeckFact], slides: list[Slide], cfg: FlagConfig, today: date) -> list[RedFlag]:
    all_years = [y for s in slides for y in years_in_text(s.text) if y <= today.year + 15]
    all_years += [y for f in facts for y in f.years]
    flags = []
    if all_years and max(all_years) < today.year - cfg.stale_years:
        flags.append(RedFlag(
            rule="stale_deck",
            severity=Severity.low,
            kind=FlagKind.coverage,
            title="Дек, вероятно, устарел",
            detail=f"Самый поздний год в материалах — {max(all_years)}.",
        ))
    past = [
        f for f in facts
        if f.metric == Metric.revenue and f.status == FactStatus.forecast and f.years and max(f.years) < today.year
    ]
    if past:
        flags.append(RedFlag(
            rule="forecast_in_past",
            severity=Severity.low,
            kind=FlagKind.coverage,
            title="Прогноз относится к уже прошедшим годам",
            detail="Запросите фактические значения за эти годы и сравните с планом.",
            slides=sorted({f.slide for f in past}),
            fact_ids=[f.id for f in past],
        ))
    return flags


def _quote_around(text: str, match: re.Match) -> str:
    start = max(0, match.start() - 60)
    end = min(len(text), match.end() + 60)
    return " ".join(text[start:end].split())


def rule_text_claims(slides: list[Slide], cfg: FlagConfig) -> list[RedFlag]:
    flags = []
    for pattern, rule, title, severity in (
        (_NO_COMPETITORS, "no_competitors_claim", "Заявлено отсутствие конкурентов или аналогов", Severity.medium),
        (_SUPERLATIVE, "superlative_claim", "Превосходная степень без подтверждения", Severity.low),
    ):
        hits = [(s.number, m) for s in slides for m in [pattern.search(s.text)] if m]
        if hits:
            number, match = hits[0]
            text = next(s.text for s in slides if s.number == number)
            flags.append(RedFlag(
                rule=rule,
                severity=severity,
                kind=FlagKind.claim,
                title=title,
                detail=f"«{_quote_around(text, match)}». Проверьте по независимым источникам.",
                slides=[n for n, _ in hits],
            ))
    return flags


def rule_period_conflict(slides: list[Slide], cfg: FlagConfig) -> list[RedFlag]:
    conflicted = []
    for slide in slides:
        if not _FINANCE_WORDS.search(slide.text):
            continue
        ranges = set(year_ranges(slide.text))
        same_span = {
            (a, b) for a in ranges for b in ranges
            if a < b and a[1] - a[0] == b[1] - b[0] and a[0] <= b[1] and b[0] <= a[1]
        }
        if same_span:
            first, second = sorted(same_span)[0]
            conflicted.append((slide.number, first, second))
    return [RedFlag(
        rule="period_conflict",
        severity=Severity.medium,
        kind=FlagKind.numeric,
        title="На слайде разные периоды для финансовых показателей",
        detail=f"Слайд {n}: указаны {a[0]}–{a[1]} и {b[0]}–{b[1]}. Уточните, к какому периоду относятся цифры.",
        slides=[n],
    ) for n, a, b in conflicted]


def rule_missing_sections(slides: list[Slide], cfg: FlagConfig) -> list[RedFlag]:
    text = "\n".join(s.text for s in slides)
    if len(text.strip()) < 300:
        return [RedFlag(
            rule="no_text_layer",
            severity=Severity.low,
            kind=FlagKind.coverage,
            title="В файле почти нет текста",
            detail="Презентация состоит из изображений. Проверка заявлений и разделов по тексту не выполнялась.",
        )]
    missing = [name for name, pattern in _SECTIONS.items() if not pattern.search(text)]
    if not missing:
        return []
    return [RedFlag(
        rule="missing_sections",
        severity=Severity.low,
        kind=FlagKind.coverage,
        title="В тексте дека не найдены разделы",
        detail=f"Не найдено упоминаний: {', '.join(missing)}. На картинках они могут быть.",
    )]


_ORDER = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}


def detect_red_flags(
    facts: list[DeckFact],
    slides: list[Slide],
    *,
    config: FlagConfig | None = None,
    today: date | None = None,
) -> list[RedFlag]:
    cfg = config or FlagConfig()
    current = today or date.today()
    trusted = [f for f in facts if not f.needs_review]
    flags: list[RedFlag] = []
    flags += rule_hockey_stick(trusted, cfg)
    flags += rule_forecast_without_fact(trusted, cfg)
    flags += rule_plan_fact_gap(trusted, cfg)
    flags += rule_inconsistent_values(trusted, cfg)
    flags += rule_market_funnel(trusted, cfg)
    flags += rule_market_without_source(trusted, slides, cfg)
    flags += rule_ambitious_share(trusted, cfg)
    flags += rule_revenue_vs_market(trusted, cfg)
    flags += rule_margins(trusted, cfg)
    flags += rule_customer_concentration(trusted, cfg)
    flags += rule_stale_plans(trusted, slides, cfg, current)
    flags += rule_text_claims(slides, cfg)
    flags += rule_period_conflict(slides, cfg)
    flags += rule_missing_sections(slides, cfg)
    return sorted(flags, key=lambda f: _ORDER[f.severity])


__all__ = ["FlagConfig", "detect_red_flags", "same_amount"]
