"""Tavily Search API adapter (MIMO_TAVILY_SETUP).

POST https://api.tavily.com/search
Authorization: Bearer <TAVILY_API_KEY>
Body: query + search_depth + max_results + include_answer=false + include_usage=true
max_results следует бюджету вызова (0..20); нулевой бюджет не выполняет сетевой запрос.
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

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
MAX_TITLE_LEN = 500
MAX_RESULTS = 20


def _normalize_item(raw: dict[str, Any], rank: int, query: str) -> dict[str, Any]:
    """Нормализация url / title / content / score (и id / published_date при наличии).

    score — оценка поисковика, не вероятность истинности вывода о компании.
    Дата публикации не подменяется датой запроса. URL не переписывается.
    """
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()[:MAX_TITLE_LEN]
    content = str(raw.get("content") or "").strip()
    published = raw.get("published_date") or None
    score = raw.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "url": url,
        "title": title,
        "content": content,
        # общее текстовое поле для нисходящих потребителей (passage у Yandex)
        "passage": content,
        "published_date": str(published) if published else None,
        "id": str(raw.get("id") or "") or None,
        "score": score,
        "rank": rank,
        "query": query,
        "source": "tavily_search",
    }


class TavilySearchProvider(BaseProvider):
    name = "tavily_search"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 25.0,
        search_depth: str | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")
        # Settings reads .env without exporting it to os.environ.
        if api_key is None and not self.api_key:
            from osint_agent.config import settings

            self.api_key = settings.tavily_api_key
        if search_depth is not None:
            self.search_depth = search_depth
        else:
            from osint_agent.config import settings

            self.search_depth = settings.tavily_search_depth or "advanced"
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            search=True,
            fetch_document=False,
            requires_key=True,
            rate_limit_note=f"search_depth={self.search_depth}; advanced = 2 кредита",
            notes=["POST /search", "max_results по бюджету (0..20)", "include_usage для учёта"],
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
                message="TAVILY_API_KEY не настроен",
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

        max_results = max(1, min(int(budget), MAX_RESULTS))
        body: dict[str, Any] = {
            "query": q,
            "search_depth": self.search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_usage": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        try:
            client = await self._get_client()
            resp = await client.post(TAVILY_SEARCH_URL, json=body, headers=headers)
            if resp.status_code in (401, 403):
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    source=self.name,
                    message="Tavily отклонил авторизацию",
                    error_code="auth_error",
                )
            if resp.status_code in (432, 433):
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    source=self.name,
                    message="Tavily: исчерпаны кредиты или лимит плана",
                    error_code="credits_exhausted",
                )
            if resp.status_code == 429:
                return SearchPage(
                    items=[],
                    status=SourceStatus.rate_limited,
                    message="Tavily: лимит частоты запросов",
                    source=self.name,
                    error_code="rate_limited",
                )
            if resp.status_code == 434:
                return SearchPage(
                    items=[],
                    status=SourceStatus.unavailable,
                    message="Tavily: временная перегрузка тарифа",
                    source=self.name,
                    error_code="unavailable",
                )
            if resp.status_code >= 500:
                return SearchPage(
                    items=[],
                    status=SourceStatus.unavailable,
                    message=f"Tavily HTTP {resp.status_code}",
                    source=self.name,
                    error_code="unavailable",
                )
            if resp.status_code >= 400:
                return SearchPage(
                    items=[],
                    status=SourceStatus.error,
                    message=f"Tavily HTTP {resp.status_code}",
                    source=self.name,
                    error_code="error",
                )
            payload = resp.json()
        except httpx.TimeoutException:
            return SearchPage(
                items=[],
                status=SourceStatus.unavailable,
                message="Tavily не ответил вовремя",
                source=self.name,
                error_code="unavailable",
            )
        except httpx.RequestError:
            return SearchPage(
                items=[],
                status=SourceStatus.unavailable,
                message="Нет связи с Tavily",
                source=self.name,
                error_code="unavailable",
            )
        except ValueError:
            return SearchPage(
                items=[],
                status=SourceStatus.error,
                message="Некорректный JSON Tavily",
                source=self.name,
                error_code="format_error",
            )

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return SearchPage(
                items=[],
                status=SourceStatus.error,
                message="В ответе Tavily нет массива results",
                source=self.name,
                error_code="format_error",
            )

        results = payload["results"]
        items = [
            _normalize_item(raw, i, q) for i, raw in enumerate(results[:max_results]) if isinstance(raw, dict)
        ]

        meta_parts = [f"search_depth={self.search_depth}"]
        usage = payload.get("usage")
        if isinstance(usage, dict) and usage.get("credits") is not None:
            meta_parts.append(f"credits={usage['credits']}")
        if payload.get("response_time") is not None:
            meta_parts.append(f"response_time={payload['response_time']}")
        if payload.get("request_id"):
            meta_parts.append(f"request_id={payload['request_id']}")
        coverage = "; ".join(meta_parts)

        return SearchPage(
            items=items,
            cursor=None,  # Tavily Search не поддерживает пагинацию
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
