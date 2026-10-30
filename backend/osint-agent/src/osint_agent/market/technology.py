"""Technology evidence (plan §14)."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    publication = "publication"
    patent = "patent"
    repository = "repository"
    case = "case"


class TechnologyEvidence(BaseModel):
    """Свидетельство без автоматических выводов о коммерческом успехе."""

    id: UUID = Field(default_factory=uuid4)
    competitor_id: UUID | None = None
    kind: EvidenceType
    external_id: str | None = None  # DOI / patent family / repo
    title: str | None = None
    url: str | None = None
    date: str | None = None
    affiliation_confirmed: bool = False
    status_note: str | None = None
    limitations: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


def merge_publications(items: list[TechnologyEvidence]) -> list[TechnologyEvidence]:
    """Склеиваем публикации по DOI/устойчивому id (plan §14)."""
    seen: dict[str, TechnologyEvidence] = {}
    out: list[TechnologyEvidence] = []
    for ev in items:
        if ev.kind != EvidenceType.publication:
            out.append(ev)
            continue
        key = (ev.external_id or ev.url or str(ev.id)).lower()
        if key in seen:
            existing = seen[key]
            if ev.url and ev.url not in (existing.raw.setdefault("alt_urls", [])):
                existing.raw.setdefault("alt_urls", []).append(ev.url)
            continue
        seen[key] = ev
        out.append(ev)
    return out


def evidence_limitations(kind: EvidenceType) -> list[str]:
    if kind == EvidenceType.publication:
        return ["Статья не доказывает работоспособность коммерческого продукта"]
    if kind == EvidenceType.patent:
        return ["Заявка не равна действующему патенту или глобальной защите"]
    if kind == EvidenceType.repository:
        return ["Звёзды репозитория не означают качество продукта"]
    return ["Рекламное обещание не равно независимому измерению"]
