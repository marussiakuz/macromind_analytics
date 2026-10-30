"""Yandex Search API adapter (plan §7).

POST https://searchapi.api.cloud.yandex.net/v2/web/search
Authorization: Api-Key <YANDEX_API_KEY>
Body: folderId + query.searchType + queryText + page (from 0) + responseFormat XML
Response: JSON rawData (Base64) → XML docs: url / title / passage
"""

from __future__ import annotations

import base64
import os
import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from osint_agent.market.providers.base import (
    BaseProvider,
    DocumentResult,
    ProviderCapabilities,
    SearchPage,
    SourceStatus,
)

YANDEX_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"
MAX_XML_BYTES = 2_000_000
MAX_TITLE_LEN = 500


def _safe_xml(text: str) -> list[dict[str, Any]]:
    """Разбор XML без внешних сущностей (plan §7)."""
    if len(text.encode("utf-8", errors="ignore")) > MAX_XML_BYTES:
        raise ValueError("XML too large")
    # элементная структура; defused-style: не используем внешние entity
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"bad xml: {exc}") from exc

    docs: list[dict[str, Any]] = []
    for doc in root.iter("doc"):
        url_el = doc.find("url")
        url = (url_el.text or "").strip() if url_el is not None else ""
        title_el = doc.find("title")
        # вложенные элементы заголовка склеиваем текстом, без исполнения разметки
        title = "".join(title_el.itertext()).strip()[:MAX_TITLE_LEN] if title_el is not None else ""
        passage = " ".join("".join(el.itertext()).strip() for el in doc.findall(".//passage"))
        if url or title:
            docs.append({"url": url, "title": title, "passage": passage})
    return docs


def _decode_raw_data(raw: str) -> str:
    if not raw:
        raise ValueError("missing rawData")
    try:
        raw_bytes = base64.b64decode(raw, validate=False)
    except Exception as exc:
        raise ValueError("bad base64") from exc
    if len(raw_bytes) > MAX_XML_BYTES:
        raise ValueError("decoded xml too large")
    return raw_bytes.decode("utf-8", errors="replace")


def _extract_xml_error(text: str) -> str | None:
    m = re.search(r"<error[^>]*>(.*?)</error>", text, re.I | re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()[:200]
    return None


class YandexSearchProvider(BaseProvider):
    name = "yandex_search"

    def __init__(
        self,
        api_key: str | None = None,
        folder_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 25.0,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("YANDEX_API_KEY", "")
        self.folder_id = folder_id if folder_id is not None else os.environ.get("YANDEX_FOLDER_ID", "")
        # Settings reads .env without exporting it to os.environ.
        from osint_agent.config import settings
        if api_key is None and not self.api_key:
            self.api_key = settings.yandex_api_key.get_secret_value()
        if folder_id is None and not self.folder_id:
            self.folder_id = settings.yandex_folder_id
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            search=True,
            fetch_document=False,
            requires_key=True,
            rate_limit_note="Бюджет модуля + квота облака; ключ не в URL",
            notes=["rawData → Base64 → XML", "страницы с 0"],
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
        if not self.api_key or not self.folder_id:
            return SearchPage(
                items=[],
                status=SourceStatus.not_configured,
                message="YANDEX_API_KEY / YANDEX_FOLDER_ID не настроены",
                source=self.name,
            )
        q = query.strip()
        if not q:
            return SearchPage(items=[], status=SourceStatus.empty, message="Пустой запрос", source=self.name)

        page = int(cursor) if cursor and cursor.isdigit() else 0
        search_type = "SEARCH_TYPE_RU" if (filters or {}).get("region") == "RU" else "SEARCH_TYPE_COM"
        body = {
            "query": {
                "searchType": search_type,
                "queryText": q,
                "page": str(page),
            },
            "folderId": self.folder_id,
            "responseFormat": "FORMAT_XML",
        }
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            client = await self._get_client()
            resp = await client.post(YANDEX_URL, json=body, headers=headers)
            if resp.status_code in (401, 403):
                return SearchPage(items=[], status=SourceStatus.error, source=self.name,
                                  message="Поиск Yandex отклонил авторизацию", error_code="auth_error")
            if resp.status_code == 429:
                return SearchPage(items=[], status=SourceStatus.rate_limited, message="Квота поиска", source=self.name)
            if resp.status_code >= 400:
                return SearchPage(
                    items=[],
                    status=SourceStatus.unavailable if resp.status_code >= 500 else SourceStatus.error,
                    message=f"Поиск HTTP {resp.status_code}",
                    source=self.name,
                )
            payload = resp.json()
        except httpx.TimeoutException:
            return SearchPage(items=[], status=SourceStatus.unavailable, message="Поиск не ответил вовремя", source=self.name)
        except httpx.RequestError:
            return SearchPage(items=[], status=SourceStatus.unavailable, message="Нет связи с сервисом поиска", source=self.name)
        except ValueError:
            return SearchPage(items=[], status=SourceStatus.error, message="Некорректный JSON поиска", source=self.name)

        raw = payload.get("rawData")
        if not isinstance(raw, str) or not raw.strip():
            # HTTP 200 без rawData — ошибка формата, не пустой успех (P06)
            return SearchPage(
                items=[],
                status=SourceStatus.error,
                message="В ответе поиска нет rawData",
                source=self.name,
            )
        try:
            xml_text = _decode_raw_data(raw)
        except ValueError as exc:
            return SearchPage(items=[], status=SourceStatus.error, message=str(exc), source=self.name)

        err = _extract_xml_error(xml_text)
        if err:
            return SearchPage(items=[], status=SourceStatus.error, message=err, source=self.name)

        try:
            docs = _safe_xml(xml_text)
        except ValueError as exc:
            return SearchPage(items=[], status=SourceStatus.error, message=str(exc), source=self.name)

        items = [
            {
                "url": d["url"],
                "title": d["title"],
                "passage": d["passage"],
                "rank": page * max(budget, 1) + i,
                "query": q,
                "page": page,
                "language": "ru" if search_type == "SEARCH_TYPE_RU" else "en",
                "source": self.name,
            }
            for i, d in enumerate(docs[:budget])
        ]
        return SearchPage(
            items=items,
            cursor=str(page + 1) if len(docs) >= budget else None,
            query=q,
            status=SourceStatus.ok if items else SourceStatus.empty,
            source=self.name,
            coverage=f"page {page}",
        )

    async def fetch_document(self, source_ref: str, budget: int = 1) -> DocumentResult:
        return DocumentResult(
            ok=False,
            status=SourceStatus.unavailable,
            message="Получение полного текста — отдельная операция с бюджетом; не реализовано в v1",
            source=self.name,
        )
