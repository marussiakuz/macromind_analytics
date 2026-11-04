"""GLiNER multi-v2.1 client (MIMO_MARKET_RECOVERY §7).

Отдельный процесс на первом сервере (127.0.0.1:8010, через SSH-туннель).
Метки на старте: компании, продукты, технологии, покупатели.
Каждая находка сохраняется с текстом, типом, координатами в тексте,
слайдом и оценкой модели.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_LABELS = ("компания", "продукт", "технология", "покупатель")


@dataclass
class GlinerResult:
    entities: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    error_code: str | None = None
    model: str = ""


class GlinerClient:
    """Асинхронный клиент отдельного процесса GLiNER."""

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ):
        if base_url is None:
            from osint_agent.config import settings

            base_url = getattr(settings, "gliner_base_url", "") or "http://127.0.0.1:8010"
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> dict[str, Any]:
        client = await self._get_client()
        r = await client.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    async def extract_entities(
        self,
        text: str,
        labels: list[str] | tuple[str, ...] = DEFAULT_LABELS,
        *,
        slide: int | None = None,
        threshold: float = 0.3,
    ) -> GlinerResult:
        """Извлечь сущности. Найденный текст, тип, координаты, слайд и оценка — в каждой записи."""
        if not text or not text.strip():
            return GlinerResult(entities=[], ok=True)
        if not labels:
            return GlinerResult(entities=[], ok=False, error="Не заданы метки", error_code="bad_request")
        body = {
            "text": text,
            "labels": list(labels),
            "slide": slide,
            "threshold": threshold,
        }
        client = await self._get_client()
        try:
            r = await client.post(f"{self.base_url}/extract", json=body)
        except httpx.TimeoutException:
            return GlinerResult(entities=[], ok=False, error="GLiNER не ответил вовремя", error_code="timeout")
        except httpx.RequestError:
            return GlinerResult(entities=[], ok=False, error="Нет связи с процессом GLiNER", error_code="unavailable")

        if r.status_code == 413:
            return GlinerResult(entities=[], ok=False, error="Текст слишком длинный для GLiNER", error_code="too_large")
        if r.status_code >= 500:
            return GlinerResult(entities=[], ok=False, error=f"GLiNER HTTP {r.status_code}", error_code="unavailable")
        if r.status_code >= 400:
            return GlinerResult(entities=[], ok=False, error=f"GLiNER HTTP {r.status_code}", error_code="error")
        try:
            data = r.json()
        except ValueError:
            return GlinerResult(entities=[], ok=False, error="Некорректный JSON GLiNER", error_code="bad_response")

        raw = data.get("entities")
        if not isinstance(raw, list):
            return GlinerResult(entities=[], ok=False, error="В ответе GLiNER нет entities", error_code="bad_response")
        entities = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            entities.append({
                "text": str(item.get("text") or ""),
                "type": str(item.get("type") or ""),
                "start": int(item.get("start") or 0),
                "end": int(item.get("end") or 0),
                "score": float(item.get("score") or 0.0),
                "slide": item.get("slide", slide),
            })
        return GlinerResult(entities=entities, ok=True, model=str(data.get("model") or ""))
