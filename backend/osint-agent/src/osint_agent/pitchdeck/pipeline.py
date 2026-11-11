"""End-to-end analysis of one deck."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from osint_agent.pitchdeck.entities import extract_entities
from osint_agent.pitchdeck.extract import assess_fact, extract_slide, should_analyze, verify_fact
from osint_agent.pitchdeck.ingest import RawSlide, read_deck
from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient
from osint_agent.pitchdeck.models import DeckAnalysis, DeckFact, Slide
from osint_agent.pitchdeck.red_flags import detect_red_flags
from osint_agent.pitchdeck.summary import build_summary

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def analyze_slide(
    client: OllamaClient,
    raw: RawSlide,
    *,
    input_mode: str = "text+image",
    verify: bool = True,
) -> list[DeckFact]:
    facts = await extract_slide(client, raw.number, raw.text, raw.image_png, input_mode)
    for fact in facts:
        if verify:
            fact.verdict = await verify_fact(client, fact, raw.text, raw.image_png, input_mode)
        assess_fact(fact, raw.text)
    return facts


async def analyze_deck(
    path: Path,
    client: OllamaClient,
    *,
    filename: str = "",
    input_mode: str = "text+image",
    progress: ProgressCallback | None = None,
    raw_slides: list[RawSlide] | None = None,
) -> DeckAnalysis:
    raws = raw_slides if raw_slides is not None else read_deck(path)
    slides: list[Slide] = []
    facts: list[DeckFact] = []
    failed = 0
    for index, raw in enumerate(raws):
        slide = Slide(number=raw.number, text=raw.text, has_image=raw.image_png is not None)
        if should_analyze(raw.text, raw.image_png is not None):
            try:
                facts.extend(await analyze_slide(client, raw, input_mode=input_mode))
            except LocalLLMError as exc:
                if exc.code == "llm_unavailable":
                    raise
                failed += 1
                slide.error = exc.code
        else:
            slide.skipped = True
        slides.append(slide)
        if progress:
            await progress(index + 1, len(raws))
    if raws and failed == len(raws):
        raise LocalLLMError("llm_bad_json", "Модель не смогла обработать ни один слайд")

    limitations = []
    if failed:
        limitations.append(f"Не обработано слайдов: {failed}.")
    without_image = sum(1 for raw in raws if raw.image_png is None)
    if without_image:
        limitations.append(
            "Для PPTX слайды не отрисовываются: анализ идёт по тексту, таблицам и данным диаграмм. "
            "Экспортируйте файл в PDF, чтобы модель видела изображения."
        )
    if slides and not any(s.text.strip() for s in slides):
        limitations.append("В файле нет текстового слоя: организации и люди не извлекались.")
    entities = await asyncio.to_thread(extract_entities, slides)
    flags = detect_red_flags(facts, slides)
    summary = await build_summary(client, slides, facts, flags)
    return DeckAnalysis(
        filename=filename or path.name,
        slide_count=len(raws),
        slides=slides,
        facts=facts,
        entities=entities,
        red_flags=flags,
        summary=summary,
        model=client.model,
        input_mode=input_mode,
        limitations=limitations,
    )
