"""Local Ollama client. Refuses non-loopback hosts so decks stay on this machine."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlparse

import httpx

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class LocalLLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def ensure_local(url: str, allow_remote: bool = False) -> str:
    host = urlparse(url).hostname or ""
    if host not in _LOOPBACK and not allow_remote:
        raise LocalLLMError(
            "remote_llm_refused",
            "Питч-деки конфиденциальны: разрешён только локальный Ollama (127.0.0.1)",
        )
    return url.rstrip("/")


def salvage_truncated(content: str) -> dict[str, Any] | None:
    """Keep complete list items when a long answer was cut off by the token limit."""
    end = content.rfind("}")
    while end > 0:
        try:
            parsed = json.loads(content[: end + 1] + "]}")
        except json.JSONDecodeError:
            end = content.rfind("}", 0, end)
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        allow_remote: bool = False,
        timeout: float = 300.0,
        num_ctx: int = 16384,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = ensure_local(base_url, allow_remote)
        self.model = model
        self.num_ctx = num_ctx
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LocalLLMError("llm_unavailable", f"Ollama недоступен: {type(exc).__name__}") from exc
        names = [m.get("name", "") for m in response.json().get("models", [])]
        return {"available": True, "model": self.model, "model_installed": self.model in names}

    async def chat_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any],
        image: bytes | None = None,
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if image:
            message["images"] = [base64.b64encode(image).decode()]
        body = {
            "model": self.model,
            "messages": [message],
            "stream": False,
            "format": schema,
            "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 42, "num_ctx": self.num_ctx, "num_predict": max_tokens},
        }
        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LocalLLMError("llm_unavailable", f"Ошибка обращения к Ollama: {type(exc).__name__}") from exc
        content = response.json().get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            parsed = salvage_truncated(content)
            if parsed is None:
                raise LocalLLMError("llm_bad_json", "Модель вернула некорректный JSON") from exc
        if not isinstance(parsed, dict):
            raise LocalLLMError("llm_bad_json", "Модель вернула не объект JSON")
        return parsed
