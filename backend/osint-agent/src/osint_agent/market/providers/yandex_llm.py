"""Yandex Studio LLM client (pattern from TechTrendSearcher radar/extract.py).

POST https://llm.api.cloud.yandex.net/v1/chat/completions
Authorization: Api-Key <YANDEX_API_KEY or RADAR_LLM_API_KEY>
model: gpt://{folder}/qwen3.6-35b-a3b

Model is not a market statistic source — interpretation only (review §4).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_ENDPOINT = "https://llm.api.cloud.yandex.net/v1/chat/completions"
DEFAULT_MODEL_TEMPLATE = "gpt://{folder}/qwen3.6-35b-a3b"
DEFAULT_TIMEOUT_S = 90.0
DEFAULT_MAX_TOKENS = 2000


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LLMSettings:
    api_key: str = ""
    folder_id: str = ""
    model_template: str = DEFAULT_MODEL_TEMPLATE
    endpoint: str = DEFAULT_ENDPOINT
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = 0.0
    reasoning_effort: str = "none"

    @property
    def model_uri(self) -> str:
        return self.model_template.replace("{folder}", self.folder_id or "NO_FOLDER")

    @property
    def headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        # Api-Key для llm.api.cloud.yandex.net (как в radar config.llm_headers)
        return {"Authorization": f"Api-Key {self.api_key}"}


def load_llm_settings_from_env() -> LLMSettings:
    # pydantic-settings читает .env, но не публиует в os.environ
    try:
        from osint_agent.config import settings as app_settings

        key = (
            os.environ.get("RADAR_LLM_API_KEY")
            or (app_settings.yandex_api_key.get_secret_value() if app_settings.yandex_api_key else "")
            or os.environ.get("YANDEX_API_KEY")
            or ""
        )
        folder = (
            os.environ.get("YANDEX_FOLDER_ID")
            or getattr(app_settings, "yandex_folder_id", "")
            or ""
        )
    except Exception:
        key = os.environ.get("RADAR_LLM_API_KEY") or os.environ.get("YANDEX_API_KEY") or ""
        folder = os.environ.get("YANDEX_FOLDER_ID") or ""
    return LLMSettings(
        api_key=key,
        folder_id=folder,
        model_template=os.environ.get("QWEN_MODEL") or DEFAULT_MODEL_TEMPLATE,
        endpoint=os.environ.get("YANDEX_LLM_URL") or DEFAULT_ENDPOINT,
    )


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    ok: bool = True
    error: str | None = None
    error_code: str | None = None


class YandexStudioLLM:
    """Независимый клиент chat/completions; TechTrendSearcher не запускаем."""

    name = "yandex_studio_llm"

    def __init__(
        self,
        settings: LLMSettings | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.settings = settings or load_llm_settings_from_env()
        self._client = client
        self._owns = client is None

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(self, system: str, payload: dict[str, Any], *, json_schema: dict | None = None) -> LLMResult:
        s = self.settings
        if not s.api_key or not s.folder_id:
            return LLMResult(
                text="",
                ok=False,
                error="Проверка недоступна: не настроен ключ Yandex Studio (YANDEX_API_KEY / RADAR_LLM_API_KEY, YANDEX_FOLDER_ID)",
                error_code="not_configured",
                model=s.model_uri,
            )
        body = {
            "model": s.model_uri,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_tokens": s.max_tokens,
            "temperature": s.temperature,
            "reasoning_effort": s.reasoning_effort,
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "market_response", "strict": True, "schema": json_schema}}
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(s.timeout_s))
        try:
            r = await self._client.post(s.endpoint, headers=s.headers, json=body)
        except httpx.TimeoutException:
            return LLMResult(text="", ok=False, error="Модель не ответила вовремя", error_code="timeout", model=s.model_uri)
        except httpx.RequestError:
            return LLMResult(text="", ok=False, error="Нет связи с Yandex Studio", error_code="unavailable", model=s.model_uri)

        if r.status_code in (401, 403):
            return LLMResult(text="", ok=False, error="Ошибка авторизации Yandex Studio", error_code="auth_error", model=s.model_uri)
        if r.status_code == 429:
            return LLMResult(text="", ok=False, error="Квота Yandex Studio", error_code="rate_limited", model=s.model_uri)
        if r.status_code >= 500:
            return LLMResult(text="", ok=False, error=f"Yandex Studio HTTP {r.status_code}", error_code="unavailable", model=s.model_uri)
        if r.status_code >= 400:
            return LLMResult(text="", ok=False, error=f"Yandex Studio HTTP {r.status_code}", error_code="error", model=s.model_uri)
        try:
            data = r.json()
        except ValueError:
            return LLMResult(text="", ok=False, error="Некорректный JSON Yandex Studio", error_code="bad_response", model=s.model_uri)

        try:
            message = data["choices"][0]["message"]
            text = message.get("content") or ""
        except (KeyError, IndexError, TypeError):
            return LLMResult(text="", ok=False, error="Нет choices в ответе модели", error_code="bad_response", model=s.model_uri)
        if not text and message.get("reasoning_content"):
            return LLMResult(
                text="",
                ok=False,
                error="Модель вернула только reasoning_content",
                error_code="bad_response",
                model=s.model_uri,
            )
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            model=s.model_uri,
            ok=True,
        )


INTERPRETATION_SYSTEM = """Ты аналитик due diligence. Не выдумывай рыночную статистику.
На входе — проверенные факты о компании и данные реестров.
Верни ТОЛЬКО JSON со схемой:
{"interpretation": [
  {"section": "russian_market",
   "statement": "вывод",
   "claim_type": "interpretation",
   "evidence_ids": ["id"],
   "calculation_ids": [],
   "limitations": ["ограничение"],
   "verification_status": "needs_review"}
],
"summary": "краткий вывод",
"risks": ["риск"],
"questions": ["вопрос для проверки"]}
claim_type ∈ interpretation | fact | forecast | team_claim | calculation.
Без подтверждающих доказательств — verification_status=needs_review, limitations обязательно.
"""


def parse_interpretation(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    data.setdefault("interpretation", [])
    data.setdefault("summary", "")
    data.setdefault("risks", [])
    data.setdefault("questions", [])
    return data
