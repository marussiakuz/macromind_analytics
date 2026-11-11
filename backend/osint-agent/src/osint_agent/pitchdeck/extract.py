"""Slide fact extraction and independent verification through the local model."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient
from osint_agent.pitchdeck.models import DeckFact, FactStatus, Metric, Verdict
from osint_agent.pitchdeck.normalize import parse_value, parse_years, value_in_text

NO_TEXT = "(текстовый слой отсутствует, смотри изображение слайда)"
TEXT_ONLY_NOTE = "Изображение слайда недоступно, опирайся только на текст."

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": [m.value for m in Metric]},
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "period": {"type": "string"},
                    "entity": {"type": "string"},
                    "status": {"type": "string", "enum": [s.value for s in FactStatus]},
                    "quote": {"type": "string"},
                },
                "required": ["metric", "label", "value", "unit", "period", "entity", "status", "quote"],
            },
        }
    },
    "required": ["facts"],
}

VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["верно", "неверно", "неясно"]}},
    "required": ["verdict"],
}

EXTRACT_PROMPT = """Ты извлекаешь числовые показатели со слайда презентации стартапа для аналитика венчурного фонда.
Извлекай только то, что явно есть на слайде. Ничего не вычисляй, не округляй и не додумывай. Если показателей нет, верни пустой список.

Нужные показатели (поле metric):
revenue — выручка; expenses — расходы; ebitda; net_profit — чистая прибыль;
market_tam, market_sam, market_som — только если на слайде прямо написано TAM, SAM или SOM; market_size — любой другой объём рынка;
market_share — доля рынка самого стартапа; customer_share — доля одного клиента в продажах;
growth_rate — темп роста выручки; headcount — сотрудники; customers — число клиентов;
investment_ask — запрашиваемые инвестиции; investment_raised — уже привлечённые; valuation — оценка компании.
Прочие числа (технические характеристики, патенты, цены) не извлекай. Показатели конкурентов и других компаний тоже не извлекай.
Бери только значения, подписанные на слайде числом. Деления оси графика — не значения: если у точки или столбца нет подписи, такого факта нет.

Правила для каждого факта:
- Один факт — одно значение за один период. Ряд по годам — отдельный факт на каждый год.
- value — только число как на слайде, без единицы и знака валюты (например «1 030» или «70+»).
- unit — единица как на слайде с учётом подписи оси или заголовка таблицы («млн руб.», «млрд $», «%», «чел.»). Знак $ или € относится к доллару или евро, не заменяй его рублём.
- Если у значения две подписи (план и «факт – 5»), выдай два отдельных факта: план со status forecast и факт со status fact.
- period — год или диапазон, к которому относится именно это значение. Определяй его по положению на графике или в таблице, а не по порядку строк текста. Если периода нет, оставь пустую строку.
- entity — заполняй, только если одинаковый показатель дан для нескольких объектов: сценарий или компания-клиент. В остальных случаях пустая строка.
- status: fact — достигнутое значение; forecast — план или прогноз (буква «П» у года, слова «план», «прогноз», «сценарий», пунктир на графике); target — цель без погодной разбивки или суммарно за несколько лет; unknown — на слайде не обозначено, факт это или план. Не считай значение прогнозом только потому, что год кажется будущим. Цели компании — не fact.
- quote — короткая подпись со слайда, по которой понятен показатель.

Текст слайда (порядок строк может быть нарушен):
---
{text}
---
{note}"""

VERIFY_PROMPT = """Проверь факт, извлечённый из слайда презентации стартапа. Оцени только соответствие слайду, а не правдивость заявления в реальности.
Факт верен, только если совпадают показатель, значение, единица, период и признак «факт/план».

Текст слайда (порядок строк может быть нарушен):
---
{text}
---
Факт: {fact}
Ответь полем verdict: «верно», «неверно» или «неясно»."""

_STATUS_RU = {
    FactStatus.fact: "достигнутое значение",
    FactStatus.forecast: "план или прогноз",
    FactStatus.target: "цель",
    FactStatus.unknown: "статус не указан",
}
_VERDICTS = {"верно": Verdict.correct, "неверно": Verdict.wrong, "неясно": Verdict.unsure}


def slide_text_for_prompt(text: str, input_mode: str) -> str:
    if input_mode == "image":
        return NO_TEXT
    return text.strip()[:6000] or NO_TEXT


def should_analyze(text: str, has_image: bool) -> bool:
    """Skip slides that cannot hold numbers: text without digits and no way to see an image."""
    return has_image or bool(re.search(r"\d", text))


_GENERIC_ENTITIES = {"компания", "компании", "стартап", "проект", "рынок", "нет", "-"}


def _clean(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def build_fact(raw: dict[str, Any], slide: int, index: int, slide_text: str) -> DeckFact | None:
    value = _clean(raw.get("value"), 60)
    if not re.search(r"\d", value):
        return None
    try:
        metric = Metric(raw.get("metric"))
    except ValueError:
        metric = Metric.other
    if metric == Metric.other:
        return None
    try:
        status = FactStatus(raw.get("status"))
    except ValueError:
        status = FactStatus.unknown
    unit = _clean(raw.get("unit"), 40)
    if unit and value.endswith(unit):
        unit = ""
    period = _clean(raw.get("period"), 40)
    parsed = parse_value(value, unit)
    return DeckFact(
        id=f"s{slide}-f{index}",
        slide=slide,
        metric=metric,
        label=_clean(raw.get("label"), 120),
        value_raw=value,
        unit_raw=unit,
        period_raw=period,
        entity="" if _clean(raw.get("entity"), 80).lower() in _GENERIC_ENTITIES else _clean(raw.get("entity"), 80),
        status=status,
        quote=_clean(raw.get("quote")),
        amount=parsed.amount,
        amount_high=parsed.amount_high,
        unit_kind=parsed.unit_kind,
        years=parse_years(period),
        value_in_text=value_in_text(value, slide_text),
    )


MIN_TEXT_LAYER = 40
RUNAWAY_MIN_FACTS = 10
RUNAWAY_MIN_GROUNDED = 0.2
RUNAWAY_MIN_REPEATS = 5
_LABELLED_MARKET = {Metric.market_tam: "TAM", Metric.market_sam: "SAM", Metric.market_som: "SOM"}


def _fix_metric(fact: DeckFact, slide_text: str) -> None:
    """Correct metric mix-ups the slide itself disproves."""
    label = _LABELLED_MARKET.get(fact.metric)
    if label and slide_text.strip() and label not in slide_text.upper():
        fact.metric = Metric.market_size
    if fact.metric == Metric.market_size and fact.unit_kind == "percent":
        fact.metric = Metric.market_share


def _split_rows(facts: list[DeckFact]) -> None:
    """Rows of one table share a metric and year; their labels tell them apart."""
    groups: dict[tuple, list[DeckFact]] = {}
    for fact in facts:
        if fact.years and not fact.entity:
            groups.setdefault((fact.metric, tuple(fact.years)), []).append(fact)
    for items in groups.values():
        if len({f.label.strip().lower() for f in items}) > 1 and len({f.value_raw for f in items}) > 1:
            for fact in items:
                fact.entity = fact.label


def has_text_layer(slide_text: str) -> bool:
    return len(slide_text.strip()) >= MIN_TEXT_LAYER


def is_runaway(facts: list[DeckFact], slide_text: str) -> bool:
    """The model sometimes loops and invents a long list that the slide text does not contain."""
    if len(facts) < RUNAWAY_MIN_FACTS:
        return False
    repeats = Counter(f.value_raw for f in facts if not f.value_in_text)
    if repeats and max(repeats.values()) >= RUNAWAY_MIN_REPEATS:
        return True
    return has_text_layer(slide_text) and sum(f.value_in_text for f in facts) / len(facts) < RUNAWAY_MIN_GROUNDED


def assess_fact(fact: DeckFact, slide_text: str) -> None:
    """A number absent from a readable text layer needs review. Scans rely on the model check."""
    if has_text_layer(slide_text):
        fact.needs_review = not fact.value_in_text
    else:
        fact.needs_review = fact.verdict != Verdict.correct


def postprocess(facts: list[DeckFact], slide_text: str) -> list[DeckFact]:
    for fact in facts:
        _fix_metric(fact, slide_text)
    seen: set[tuple] = set()
    unique = []
    for fact in facts:
        # Dense tables make the model repeat the list; plan and fact differ by value anyway.
        key = (fact.metric, fact.value_raw, tuple(fact.years) or fact.period_raw, fact.entity.lower(), fact.label.lower())
        if key not in seen:
            seen.add(key)
            unique.append(fact)
    _split_rows(unique)
    return unique


async def extract_slide(
    client: OllamaClient,
    slide: int,
    text: str,
    image: bytes | None,
    input_mode: str = "text+image",
) -> list[DeckFact]:
    use_image = image if input_mode != "text" else None
    note = "" if use_image else TEXT_ONLY_NOTE
    prompt = EXTRACT_PROMPT.format(text=slide_text_for_prompt(text, input_mode), note=note)
    data = await client.chat_json(prompt, schema=EXTRACT_SCHEMA, image=use_image, max_tokens=6000)
    raw_facts = data.get("facts")
    if not isinstance(raw_facts, list):
        return []
    facts = [build_fact(r, slide, i, text) for i, r in enumerate(raw_facts) if isinstance(r, dict)]
    cleaned = [f for f in facts if f is not None]
    if is_runaway(cleaned, text):
        raise LocalLLMError("llm_runaway", "Модель выдала список чисел, которых нет на слайде")
    return postprocess(cleaned, text)


def describe_fact(fact: DeckFact) -> str:
    parts = [fact.label or fact.metric.value, f"{fact.value_raw} {fact.unit_raw}".strip()]
    if fact.period_raw:
        parts.append(f"период: {fact.period_raw}")
    if fact.entity:
        parts.append(f"относится к: {fact.entity}")
    parts.append(_STATUS_RU[fact.status])
    return "; ".join(parts)


async def verify_fact(
    client: OllamaClient,
    fact: DeckFact,
    text: str,
    image: bytes | None,
    input_mode: str = "text+image",
) -> Verdict:
    use_image = image if input_mode != "text" else None
    prompt = VERIFY_PROMPT.format(text=slide_text_for_prompt(text, input_mode), fact=describe_fact(fact))
    data = await client.chat_json(prompt, schema=VERIFY_SCHEMA, image=use_image, max_tokens=30)
    return _VERDICTS.get(str(data.get("verdict", "")).strip().lower(), Verdict.unsure)
