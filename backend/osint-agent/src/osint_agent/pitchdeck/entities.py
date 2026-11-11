"""Named entities and company identifiers from slide text.

Natasha finds organizations and people; INN and OGRN are matched by pattern and checksum.
Slides without a text layer give nothing here. Names are candidates for an analyst, not verified links.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from osint_agent.connectors.egrul import validate_inn
from osint_agent.pitchdeck.models import DeckEntity, Slide

_INN = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_OGRN = re.compile(r"(?<!\d)(\d{13})(?!\d)")
_KEEP = {"ORG": "organization", "PER": "person"}
_MIN_LENGTH = 3


@lru_cache(maxsize=1)
def _load_tagger() -> tuple[Any, Any, type]:
    from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter

    return Segmenter(), NewsNERTagger(NewsEmbedding()), Doc


def _valid_ogrn(value: str) -> bool:
    return int(value[-1]) == int(value[:-1]) % 11 % 10


def _normal_key(text: str) -> str:
    return re.sub(r"[\s«»\"'.,]+", " ", text).strip().lower()


def extract_entities(slides: list[Slide]) -> list[DeckEntity]:
    found: dict[tuple[str, str], DeckEntity] = {}

    def remember(kind: str, text: str, slide: int) -> None:
        name = " ".join(text.split()).strip(" ,.;:")
        if len(name) < _MIN_LENGTH:
            return
        key = (kind, _normal_key(name))
        entity = found.setdefault(key, DeckEntity(kind=kind, text=name))
        if slide not in entity.slides:
            entity.slides.append(slide)
        entity.mentions += 1

    for slide in slides:
        for match in _INN.findall(slide.text):
            if validate_inn(match):
                remember("inn", match, slide.number)
        for match in _OGRN.findall(slide.text):
            if _valid_ogrn(match):
                remember("ogrn", match, slide.number)

    segmenter, tagger, doc_class = _load_tagger()
    for slide in slides:
        if not slide.text.strip():
            continue
        doc = doc_class(slide.text)
        doc.segment(segmenter)
        doc.tag_ner(tagger)
        for span in doc.spans:
            kind = _KEEP.get(span.type)
            if kind:
                remember(kind, span.text, slide.number)
    return sorted(found.values(), key=lambda e: (-e.mentions, e.kind, e.text))
