"""OpenAlex works search adapter (plan §7 OpenAlex).

HTTP GET https://api.openalex.org/works
Authorization: Bearer <OPENALEX_API_KEY>  (header, not query — fewer log leaks)
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

from osint_agent.market.providers.base import (
    BaseProvider,
    DocumentResult,
    ProviderCapabilities,
    SearchPage,
    SourceStatus,
)

OPENALEX_URL = "https://api.openalex.org/works"
# Не переносить paid/limit из старого клиента без проверки
DEFAULT_PER_PAGE = 10
MAX_ABSTRACT_CHARS = 20000


def rebuild_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """abstract_inverted_index → текст по позициям (plan §7 OpenAlex)."""
    if not inverted_index:
        return None
    if not isinstance(inverted_index, dict):
        raise ValueError("abstract_inverted_index must be a dict")
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        if not isinstance(idxs, (list, tuple)):
            raise ValueError("abstract positions must be a list")
        for i in idxs:
            if not isinstance(i, int) or i < 0 or i > 100000:
                raise ValueError("invalid abstract position")
            positions.append((i, str(word)))
    positions.sort(key=lambda p: p[0])
    if len(positions) > MAX_ABSTRACT_CHARS:
        raise ValueError("abstract too large")
    return " ".join(w for _, w in positions) or None


class OpenAlexProvider(BaseProvider):
    name = "openalex"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "")
        if api_key is None and not self.api_key:
            from osint_agent.config import settings
            self.api_key = settings.openalex_api_key.get_secret_value()
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            search=True,
            fetch_document=False,
            requires_key=bool(self.api_key),
            rate_limit_note="Передавать бюджет запросов явно; квота поставщика отдельно",
            notes=["Без ключа — только явный ограниченный режим"],
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        budget: int = 10,
    ) -> SearchPage:
        if not query.strip():
            return SearchPage(items=[], status=SourceStatus.empty, message="Пустой запрос", source=self.name)

        params: dict[str, Any] = {
            "search": query.strip(),
            "per_page": min(max(budget, 1), 25),
            "select": "id,doi,title,publication_date,abstract_inverted_index,primary_location,authorships,cited_by_count",
        }
        if filters:
            if filters.get("from_publication_date"):
                params["filter"] = f"from_publication_date:{filters['from_publication_date']}"
            if filters.get("to_publication_date"):
                f = params.get("filter", "")
                end = f"to_publication_date:{filters['to_publication_date']}"
                params["filter"] = f"{f},{end}" if f else end
        if cursor:
            params["cursor"] = cursor

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # без ключа — не переключаться скрыто на анонимный полный режим
        if not self.api_key:
            return SearchPage(
                items=[],
                status=SourceStatus.not_configured,
                message="OPENALEX_API_KEY не настроен",
                source=self.name,
            )

        try:
            client = await self._get_client()
            resp = await client.get(OPENALEX_URL, params=params, headers=headers)
            if resp.status_code == 429:
                return SearchPage(items=[], status=SourceStatus.rate_limited, message="Квота OpenAlex", source=self.name)
            if resp.status_code >= 500:
                return SearchPage(items=[], status=SourceStatus.unavailable, message=f"OpenAlex HTTP {resp.status_code}", source=self.name)
            if resp.status_code >= 400:
                return SearchPage(items=[], status=SourceStatus.error, message=f"OpenAlex HTTP {resp.status_code}", source=self.name)
            payload = resp.json()
        except httpx.TimeoutException:
            return SearchPage(items=[], status=SourceStatus.unavailable, message="OpenAlex не ответил вовремя", source=self.name)
        except httpx.RequestError:
            return SearchPage(items=[], status=SourceStatus.unavailable, message="Нет связи с OpenAlex", source=self.name)
        except ValueError:
            return SearchPage(items=[], status=SourceStatus.error, message="Некорректный JSON OpenAlex", source=self.name)

        results = payload.get("results") or []
        items: list[dict[str, Any]] = []
        abstract_errors = 0
        for row in results:
            if not isinstance(row, dict):
                continue
            try:
                abstract = rebuild_abstract(row.get("abstract_inverted_index"))
            except ValueError:
                abstract = None
                abstract_errors += 1
            items.append(
                {
                    "id": row.get("id"),
                    "doi": row.get("doi"),
                    "title": row.get("title"),
                    "publication_date": row.get("publication_date"),
                    "abstract": abstract,
                    "cited_by_count": row.get("cited_by_count"),
                    "authorships": row.get("authorships"),
                    "primary_location": row.get("primary_location"),
                    "source": self.name,
                }
            )

        status = SourceStatus.ok if items else SourceStatus.empty
        message = None
        if abstract_errors:
            status = SourceStatus.partial
            message = f"Не разобрана аннотация у {abstract_errors} работ"

        next_cursor = (payload.get("meta") or {}).get("next_cursor")
        return SearchPage(
            items=items,
            cursor=next_cursor,
            query=query,
            status=status,
            message=message,
            source=self.name,
            coverage=f"{len(items)} works",
        )

    async def fetch_document(self, source_ref: str, budget: int = 1) -> DocumentResult:
        return DocumentResult(
            ok=False,
            status=SourceStatus.unavailable,
            message="Загрузка полного текста OpenAlex не поддерживается адаптером",
            source=self.name,
        )
