"""Local llama-server LLM client (OpenAI-compatible /v1/chat/completions).

MIMO Market Recovery §3 — swappable model provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from osint_agent.market.providers.yandex_llm import LLMResult, LLMError


class LocalLLMSettings:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        model: str = "local",
        api_key: str = "",
        timeout_s: float = 180.0,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        context_size: int = 4096,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model or "local"
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.context_size = context_size

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


class LocalLLM:
    """OpenAI-compatible chat/completions client for llama-server."""

    name = "local_llm"

    def __init__(
        self,
        settings: LocalLLMSettings | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.settings = settings or load_local_llm_settings()
        self._client = client
        self._owns = client is None

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def readiness(self) -> LLMResult:
        """Cheap model readiness probe; never generates a completion."""
        s = self.settings
        url = s.base_url.removesuffix('/v1') + '/health'
        try:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=httpx.Timeout(s.timeout_s))
            response = await self._client.get(url, headers=s.headers, timeout=5.0)
            if response.status_code >= 400:
                return LLMResult(text='', ok=False, error_code='unavailable', model=s.model)
            data = response.json()
            if not isinstance(data, dict) or data.get('status') != 'ok':
                return LLMResult(text='', ok=False, error_code='unavailable', model=s.model)
            return LLMResult(text='', ok=True, model=s.model)
        except (httpx.RequestError, ValueError):
            return LLMResult(text='', ok=False, error_code='unavailable', model=s.model)

    async def complete(
        self, system: str, payload: dict[str, Any], *, json_schema: dict | None = None
    ) -> LLMResult:
        s = self.settings
        body: dict[str, Any] = {
            "model": s.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_tokens": s.max_tokens,
            "temperature": s.temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "market_response", "strict": True, "schema": json_schema},
            }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(s.timeout_s))
        try:
            r = await self._client.post(s.endpoint, headers=s.headers, json=body)
        except httpx.TimeoutException:
            return LLMResult(text="", ok=False, error="Модель не ответила вовремя", error_code="timeout", model=s.model)
        except httpx.RequestError:
            return LLMResult(text="", ok=False, error=f"Нет связи с локальной моделью ({s.base_url})", error_code="unavailable", model=s.model)

        if r.status_code == 401:
            return LLMResult(text="", ok=False, error="Ошибка авторизации локальной модели", error_code="auth_error", model=s.model)
        if r.status_code == 429:
            return LLMResult(text="", ok=False, error="Лимит запросов локальной модели", error_code="rate_limited", model=s.model)
        if r.status_code >= 500:
            return LLMResult(text="", ok=False, error=f"Локальная модель HTTP {r.status_code}", error_code="unavailable", model=s.model)
        if r.status_code >= 400:
            # Безопасная диагностика: только сообщение ошибки сервера (без ключей и содержимого).
            message = ""
            try:
                err = (r.json() or {}).get("error") or {}
                message = str(err.get("message") or "")[:300]
                if err.get("type") == "exceed_context_size_error":
                    n_prompt = int(err.get("n_prompt_tokens") or 0)
                    n_ctx = int(err.get("n_ctx") or 0)
                    # Один повтор: prompt помещается, но max_tokens не оставлял места под ответ.
                    if 0 < n_prompt < n_ctx:
                        body["max_tokens"] = max(256, n_ctx - n_prompt - 16)
                        try:
                            r = await self._client.post(s.endpoint, headers=s.headers, json=body)
                            if r.status_code < 400:
                                return self._parse_completion(r, s)
                        except Exception:
                            pass
            except Exception:
                pass
            detail = f": {message}" if message else ""
            return LLMResult(text="", ok=False, error=f"Локальная модель HTTP {r.status_code}{detail}",
                             error_code="error", model=s.model)
        return self._parse_completion(r, s)

    def _parse_completion(self, resp: httpx.Response, s: LocalLLMSettings) -> LLMResult:
        try:
            data = resp.json()
        except ValueError:
            return LLMResult(text="", ok=False, error="Некорректный JSON локальной модели", error_code="bad_response", model=s.model)

        try:
            message = data["choices"][0]["message"]
            text = message.get("content") or ""
        except (KeyError, IndexError, TypeError):
            return LLMResult(text="", ok=False, error="Нет choices в ответе модели", error_code="bad_response", model=s.model)
        if not text and message.get("reasoning_content"):
            return LLMResult(
                text="",
                ok=False,
                error="Модель вернула только reasoning_content",
                error_code="bad_response",
                model=s.model,
            )
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            model=data.get("model") or s.model,
            ok=True,
        )


def load_local_llm_settings() -> LocalLLMSettings:
    try:
        from osint_agent.config import settings as app_settings

        return LocalLLMSettings(
            base_url=app_settings.llm_base_url or "http://127.0.0.1:8080/v1",
            model=app_settings.llm_model or "local",
            api_key=app_settings.llm_api_key.get_secret_value() if app_settings.llm_api_key else "",
            timeout_s=app_settings.llm_timeout_s,
            max_tokens=app_settings.llm_max_tokens,
            temperature=app_settings.llm_temperature,
            context_size=app_settings.llm_context_size,
        )
    except Exception:
        return LocalLLMSettings()
