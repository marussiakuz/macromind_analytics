"""Unified source adapter interface (plan §7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceStatus(str, Enum):
    ok = "ok"
    empty = "empty"
    unavailable = "unavailable"
    not_configured = "not_configured"
    rate_limited = "rate_limited"
    partial = "partial"
    error = "error"


@dataclass
class SearchPage:
    items: list[dict[str, Any]]
    cursor: str | None = None
    query: str = ""
    fetched_at: str | None = None
    coverage: str | None = None
    status: SourceStatus = SourceStatus.ok
    message: str | None = None
    source: str = ""
    error_code: str | None = None


@dataclass
class DocumentResult:
    ok: bool
    content: str | None = None
    status: SourceStatus = SourceStatus.ok
    message: str | None = None
    source: str = ""
    url: str | None = None


@dataclass
class ProviderCapabilities:
    name: str
    search: bool = True
    fetch_document: bool = False
    requires_key: bool = True
    rate_limit_note: str | None = None
    notes: list[str] = field(default_factory=list)


class BaseProvider(ABC):
    """search / fetch_document / capabilities (plan §7)."""

    name: str = "base"

    @abstractmethod
    async def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        budget: int = 10,
    ) -> SearchPage: ...

    async def fetch_document(self, source_ref: str, budget: int = 1) -> DocumentResult:
        return DocumentResult(
            ok=False,
            status=SourceStatus.unavailable,
            message="Загрузка документа не поддерживается этим источником",
            source=self.name,
        )
