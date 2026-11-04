"""Exa Search API adapter (MIMO_EXA_SETUP).

POST https://api.exa.ai/search
x-api-key: <EXA_API_KEY> (допустим и Authorization: Bearer)
Body: query + type=auto + contents.highlights + numResults (по бюджету вызова)
Response: requestId / results[{id,url,title,publishedDate,score,highlights}] / costDollars / searchTime
Search не поддерживает пагинацию — cursor всегда None.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from osint_agent.market.providers.base import (
    BaseProvider,
    DocumentResult,
    ProviderCapabilities,
    SearchPage,
    SourceStatus,
)

EXA_SEARCH_URL = "https://api.exa.ai/search"
MAX_TITLE_LEN = 500
MAX_NUM_RESULTS = 100


def _normalize_item(raw: dict[str, Any], rank: int, query: str) -> dict[str, Any]:
    """Нормализация url / title / highlights / publishedDate / id / score.

    URL не переписывается (путь и значимые параметры сохраняются).
    Дата публикации не подменяется датой запроса.
    """
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()[:MAX_TITLE_LEN]
    highlights_raw = raw.get("highlights")
    if isinstance(highlights_raw, str):
        highlights_raw = [highlights_raw]
    highlights = [str(h).strip() for h in (highlights_raw or []) if str(h or "").strip()]
    published = raw.get("publishedDate") or raw.get("published_date") or None
    score = raw.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "url": url,
        "title": title,
        "highlights": highlights,
        # общее текстовое поле для нисходящих потребителей (passage у Yandex)
        "passage": "\n".join(highlights),
        "published_date": str(published) if published else None,
        "id": str(raw.get("id") or "") or None,
        "score": score,
        "rank": rank,
        "query": query,
        "source": "exa_search",
    }


class ExaSearchProvider(BaseProvider):
    name = "exa_search"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 25.0,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("EXA_API_KEY", "")
        # Settings reads .env without exporting it to os.environ.
        if api_key is None and not self.api_key:
            from osint_agent.config import settings

            self.api_key = settings.exa_api_key.get_secret_value()
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            search=True,
            fetch_document=False,
            requires_key=True,
            rate_limit_note="Стоимость ответа в costDollars; ключ не в URL",
            notes=["POST /search", "numResults по бюджету (1..100)", "без пагинации"],
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
        if not self.api_key:
            return SearchPage(
                items=[],
                status=SourceStatus.not_configured,
                message="EXA_API_KEY не настроен",
                source=self.name,
                error_code="not_configured",
            )
        q = query.strip()
        if not q:
            return SearchPage(items=[], status=SourceStatus.empty, message="Пустой запрос", source=self.name)
        if budget <= 0:
            return SearchPage(
                items=[],
                status=SourceStatus.empty,
                message="Нулевой бюджет — сетевой запрос не выполнялся",
                source=self.name,
                query=q,
            )

        num_results = max(1, min(int(budget), MAX_NUM_RESULTS))
        body: dict[str, Any] = {
            "query": q,
            "type": "auto",
            "contents": {"highlights": True},
            "numResults": num_results,
        }
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}

        try:
            client = await self._get_client()
            resp = await client.post(EXA_SEARCH_URL, json=body, headers=headers)
            if resp.status_code in (401, 403):
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    source=self.name,
                    message="Exa отклонил авторизацию",
                    error_code="auth_error",
                )
            if resp.status_code == 402:
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    source=self.name,
                    message="Exa: проблема оплаты или баланса",
                    error_code="payment_required",
                )
            if resp.status_code == 429:
                return SearchPage(
                    items=[],
                    status=SourceStatus.rate_limited,
                    message="Exa: лимит частоты запросов",
                    source=self.name,
                    error_code="rate_limited",
                )
            if resp.status_code >= 500:
                return SearchPage(
                    items=[],
                    status=SourceStatus.unavailable,
                    message=f"Exa HTTP {resp.status_code}",
                    source=self.name,
                    error_code="unavailable",
                )
            if resp.status_code >= 400:
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    message=f"Exa HTTP {resp.status_code}",
                    source=self.name,
                    error_code="error",
                )
            payload = resp.json()
        except httpx.TimeoutException:
            return SearchPage(
                items=[],
                status=SourceStatus.unavailable,
                message="Exa не ответил вовремя",
                source=self.name,
                error_code="unavailable",
            )
        except httpx.RequestError:
            return SearchPage(
                items=[],
                status=SourceStatus.unavailable,
                message="Нет связи с Exa",
                source=self.name,
                error_code="unavailable",
            )
        except ValueError:
            return SearchPage(
                items=[],
                status=SourceStatus.error,
                message="Некорректный JSON Exa",
                source=self.name,
                error_code="format_error",
            )

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return SearchPage(
                items=[],
                status=SourceStatus.error,
                message="В ответе Exa нет массива results",
                source=self.name,
                error_code="format_error",
            )

        results = payload["results"]
        items = [
            _normalize_item(raw, i, q) for i, raw in enumerate(results[:num_results]) if isinstance(raw, dict)
        ]

        meta_parts = []
        for key in ("requestId", "searchTime", "costDollars"):
            value = payload.get(key)
            if value is not None:
                meta_parts.append(f"{key}={value}")
        coverage = "; ".join(meta_parts) or None

        return SearchPage(
            items=items,
            cursor=None,  # Search не поддерживает пагинацию
            query=q,
            status=SourceStatus.ok if items else SourceStatus.empty,
            source=self.name,
            coverage=coverage,
        )

    async def fetch_document(self, source_ref: str, budget: int = 1) -> DocumentResult:
        return DocumentResult(
            ok=False,
            status=SourceStatus.unavailable,
            message="Получение полного текста — отдельная операция; используется загрузчик MMA",
            source=self.name,
        )
