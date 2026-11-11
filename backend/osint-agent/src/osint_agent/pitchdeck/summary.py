"""Short deck summary. Every number must come from extracted facts, otherwise a template is used."""

from __future__ import annotations

import re
from typing import Any

from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient
from osint_agent.pitchdeck.models import DeckFact, DeckSummary, FactStatus, Metric, RedFlag, Slide

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

SUMMARY_PROMPT = """Напиши краткую сводку питч-дека стартапа для аналитика венчурного фонда: 3–5 предложений по-русски.
Что делает компания, для какого рынка, какие ключевые цифры заявлены и что нужно проверить в первую очередь.
Все показатели — заявления компании, а не проверенные данные. Используй только сведения ниже.
Нельзя добавлять числа, которых нет в списке фактов. Не давай инвестиционных рекомендаций.

Текст первых слайдов:
---
{intro}
---
Факты:
{facts}

Что проверить:
{flags}"""

_STATUS_RU = {
    FactStatus.fact: "факт",
    FactStatus.forecast: "прогноз",
    FactStatus.target: "цель",
    FactStatus.unknown: "статус неясен",
}
_METRIC_RU = {
    Metric.revenue: "выручка",
    Metric.expenses: "расходы",
    Metric.ebitda: "EBITDA",
    Metric.net_profit: "чистая прибыль",
    Metric.market_tam: "TAM",
    Metric.market_sam: "SAM",
    Metric.market_som: "SOM",
    Metric.market_size: "объём рынка",
    Metric.market_share: "доля рынка",
    Metric.customer_share: "доля клиента",
    Metric.growth_rate: "темп роста",
    Metric.headcount: "сотрудники",
    Metric.customers: "клиенты",
    Metric.investment_ask: "запрос инвестиций",
    Metric.investment_raised: "привлечено",
    Metric.valuation: "оценка",
}
_PRIORITY = [
    Metric.investment_ask,
    Metric.revenue,
    Metric.market_tam,
    Metric.market_sam,
    Metric.market_som,
    Metric.market_size,
    Metric.ebitda,
    Metric.valuation,
    Metric.investment_raised,
    Metric.market_share,
    Metric.headcount,
    Metric.customers,
]
_NUM = re.compile(r"\d[\d\s ]*(?:[.,]\d+)?")


def _fact_line(fact: DeckFact) -> str:
    period = f", {fact.period_raw}" if fact.period_raw else ""
    entity = f", {fact.entity}" if fact.entity else ""
    return (
        f"- {_METRIC_RU.get(fact.metric, fact.metric.value)}: {fact.value_raw} {fact.unit_raw}".rstrip()
        + f"{period}{entity} ({_STATUS_RU[fact.status]}, слайд {fact.slide})"
    )


def _key_facts(facts: list[DeckFact], limit: int = 30) -> list[DeckFact]:
    trusted = [f for f in facts if not f.needs_review]
    ordered = sorted(
        trusted,
        key=lambda f: (_PRIORITY.index(f.metric) if f.metric in _PRIORITY else 99, f.years[-1] if f.years else 0),
    )
    return ordered[:limit]


def _normal_number(token: str) -> str:
    return re.sub(r"[\s ]", "", token).replace(",", ".").rstrip(".")


def numbers_grounded(text: str, allowed_sources: list[str]) -> bool:
    """Every number in the text must appear in the facts, flags or intro given to the model."""
    allowed: set[str] = set()
    for source in allowed_sources:
        allowed.update(_normal_number(n) for n in _NUM.findall(source))
    return all(_normal_number(n) in allowed for n in _NUM.findall(text))


def template_summary(facts: list[DeckFact], flags: list[RedFlag], note: str = "") -> DeckSummary:
    lines = []
    key = _key_facts(facts, limit=6)
    if key:
        lines.append(
            "Заявленные показатели: "
            + "; ".join(
                f"{_METRIC_RU.get(f.metric, f.metric.value)} {f.value_raw} {f.unit_raw}".rstrip()
                + (f" ({f.period_raw}, {_STATUS_RU[f.status]})" if f.period_raw else f" ({_STATUS_RU[f.status]})")
                for f in key
            )
            + "."
        )
    else:
        lines.append("Надёжно извлечённых числовых показателей нет: требуется ручной просмотр.")
    if flags:
        lines.append("Проверить в первую очередь: " + "; ".join(f.title.lower() for f in flags[:3]) + ".")
    return DeckSummary(text=" ".join(lines), generated_by="template", note=note)


async def build_summary(
    client: OllamaClient,
    slides: list[Slide],
    facts: list[DeckFact],
    flags: list[RedFlag],
) -> DeckSummary:
    intro = "\n".join(s.text for s in slides[:4] if s.text.strip())[:2500]
    key = _key_facts(facts)
    fact_block = "\n".join(_fact_line(f) for f in key) or "нет надёжно извлечённых показателей"
    flag_block = "\n".join(f"- {f.title}" for f in flags[:5]) or "нет"
    prompt = SUMMARY_PROMPT.format(intro=intro or "текста нет", facts=fact_block, flags=flag_block)
    try:
        data = await client.chat_json(prompt, schema=SUMMARY_SCHEMA, max_tokens=500)
    except LocalLLMError as exc:
        return template_summary(facts, flags, note=f"Модель не ответила: {exc.code}")
    text = " ".join(str(data.get("summary", "")).split())
    if not text:
        return template_summary(facts, flags, note="Модель вернула пустую сводку")
    if not numbers_grounded(text, [intro, fact_block]):
        return template_summary(facts, flags, note="Сводка модели содержала числа не из фактов и отброшена")
    return DeckSummary(text=text, generated_by="llm")
