"""Client for embedding service on server 2 (Task2 RAG §7)."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0
DIM = 1024


def default_url() -> str:
    """Resolve at call time — apply_knowledge_env() runs after import."""
    return (
        os.environ.get("EMBEDDING_BASE_URL")
        or os.environ.get("EMBEDDING_SERVICE_URL")
        or "http://127.0.0.1:8091"
    ).rstrip("/")


def query_vector(payload: dict[str, Any]) -> list[float]:
    """Unwrap single-query embedding from /internal/embeddings response.

    API returns `vectors: [[...]]`; retrieval expects one flat 1024-dim list.
    """
    vectors = payload.get("vectors") or []
    return list(vectors[0]) if vectors else []


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    revision: str
    dimension: int
    input_type: str
    prompt_tokens: int
    elapsed_ms: float
    ok: bool = True
    error: str | None = None
    error_code: str | None = None


class EmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = (base_url or default_url()).rstrip("/")
        self._client = client
        self._owns = client is None
        self._timeout = timeout

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def ready(self) -> dict[str, Any]:
        c = await self._http()
        try:
            r = await c.get(f"{self.base_url}/health/ready")
            return r.json()
        except Exception as exc:  # noqa: BLE001
            return {"ready": False, "error": str(exc)[:200]}

    async def embed(self, texts: list[str], input_type: str = "document") -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                [], "", DIM, input_type, 0, 0.0, ok=False, error="Нет текстов", error_code="empty"
            )
        c = await self._http()
        try:
            r = await c.post(
                f"{self.base_url}/internal/embeddings",
                json={"input_type": input_type, "texts": texts},
            )
        except httpx.TimeoutException:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Сервис эмбеддингов не ответил вовремя",
                error_code="timeout",
            )
        except httpx.RequestError:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Нет связи с сервисом эмбеддингов",
                error_code="unavailable",
            )
        if r.status_code == 422:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Вход отклонён сервисом",
                error_code="invalid_input",
            )
        if r.status_code == 429:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Очередь эмбеддингов переполнена",
                error_code="rate_limited",
            )
        if r.status_code == 503:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Модель не готова",
                error_code="not_ready",
            )
        if r.status_code >= 400:
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error=f"Сервис эмбеддингов HTTP {r.status_code}",
                error_code="error",
            )
        try:
            data = r.json()
            vectors = data["vectors"]
            if (
                data.get("dimension") != DIM
                or not isinstance(vectors, list)
                or len(vectors) != len(texts)
                or not data.get("revision")
            ):
                raise ValueError("embedding response shape")
            for vector in vectors:
                if (
                    not isinstance(vector, list)
                    or len(vector) != DIM
                    or any(
                        isinstance(x, bool)
                        or not isinstance(x, (int, float))
                        or not math.isfinite(x)
                        for x in vector
                    )
                    or not any(vector)
                ):
                    raise ValueError("invalid embedding vector")
            prompt_tokens = int(data.get("prompt_tokens") or 0)
            elapsed_ms = float(data.get("elapsed_ms") or 0.0)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return EmbeddingResult(
                [],
                "",
                DIM,
                input_type,
                0,
                0.0,
                ok=False,
                error="Некорректный ответ эмбеддингов",
                error_code="bad_response",
            )
        return EmbeddingResult(
            vectors=vectors,
            revision=data.get("revision", ""),
            dimension=data.get("dimension", DIM),
            input_type=input_type,
            prompt_tokens=prompt_tokens,
            elapsed_ms=elapsed_ms,
            ok=True,
        )
