"""Knowledge base models (Task2 RAG §5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_type: str
    name: str
    identifiers: dict[str, Any] = Field(default_factory=dict)
    alt_names: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class EntityRelation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject_id: UUID
    relation: str
    object_id: UUID | None = None
    object_label: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    evidence_id: UUID | None = None


class Document(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    origin_id: str | None = None
    source_type: str
    url: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=_now)
    storage_path: str | None = None
    checksum: str | None = None
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID | None = None
    entity_id: UUID | None = None
    claim_type: str = "fact"
    statement: str
    locator: str | None = None
    quote: str | None = None
    period: str | None = None
    geography: str | None = None
    unit: str | None = None
    verification_status: str = "unreviewed"
    created_at: datetime = Field(default_factory=_now)


class Chunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    evidence_id: UUID | None = None
    text: str
    lang: str | None = None
    token_count: int | None = None
    embedding: list[float] | None = None


class ResearchRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str
    status: str = "queued"
    owner: str | None = None
    input_hash: str | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
