"""Read PDF/PPTX decks into slides with text and, for PDF, a rendered image."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from pptx import Presentation

MAX_SLIDES = 150
_MAX_SIDE = 1600


class DeckReadError(Exception):
    pass


@dataclass
class RawSlide:
    number: int
    text: str
    image_png: bytes | None = None


def _read_pdf(path: Path) -> list[RawSlide]:
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        raise DeckReadError("Не удалось открыть PDF (файл повреждён или защищён паролем)") from exc
    try:
        if len(pdf) > MAX_SLIDES:
            raise DeckReadError(f"В файле больше {MAX_SLIDES} страниц")
        slides = []
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            text = textpage.get_text_bounded().replace("\r\n", "\n").strip()
            textpage.close()
            width, height = page.get_size()
            scale = min(2.0, _MAX_SIDE / max(width, height, 1))
            image = page.render(scale=scale).to_pil().convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            page.close()
            slides.append(RawSlide(index + 1, text, buffer.getvalue()))
        return slides
    finally:
        pdf.close()


def _pptx_shape_text(shape) -> list[str]:
    parts: list[str] = []
    if shape.has_text_frame:
        parts.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    if getattr(shape, "has_chart", False) and shape.has_chart:
        chart = shape.chart
        for plot in chart.plots:
            categories = [str(c) for c in plot.categories]
            for series in plot.series:
                values = ", ".join(f"{c}: {v}" for c, v in zip(categories, series.values))
                parts.append(f"{series.name}: {values}")
    for child in getattr(shape, "shapes", []):
        parts.extend(_pptx_shape_text(child))
    return parts


def _read_pptx(path: Path) -> list[RawSlide]:
    try:
        presentation = Presentation(str(path))
    except Exception as exc:  # python-pptx raises several unrelated types on bad files
        raise DeckReadError("Не удалось открыть PPTX") from exc
    if len(presentation.slides) > MAX_SLIDES:
        raise DeckReadError(f"В файле больше {MAX_SLIDES} слайдов")
    slides = []
    for index, slide in enumerate(presentation.slides):
        parts: list[str] = []
        for shape in slide.shapes:
            parts.extend(_pptx_shape_text(shape))
        slides.append(RawSlide(index + 1, "\n".join(p for p in parts if p.strip()).strip()))
    return slides


def read_deck(path: Path) -> list[RawSlide]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".pptx":
        return _read_pptx(path)
    raise DeckReadError("Поддерживаются только PDF и PPTX")


def sniff_kind(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return ".pdf"
    if head.startswith(b"PK\x03\x04"):
        return ".pptx"
    return None
