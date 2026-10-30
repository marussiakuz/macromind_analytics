"""Business Incognita connector — NOT enabled until source agreement (MIMO §2/§4).

Status: requires_source_agreement
Public channel visibility is NOT a license to mass-ingest into RAG.
Telegram ToS (content-licensing / LLM clause) require explicit consent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUS = "requires_source_agreement"

# What must be in place before any live Telegram history call.
REQUIRED_ACCESS = [
    "Telegram api_id + api_hash (от владельца/интегратора, не из чужого репозитория)",
    "Пользовательская MTProto-сессия (не обычный bot) для messages.getHistory",
    "Письменное согласие администратора канала на сбор и индексацию материалов в RAG",
    "Подтверждение прав на вложенные чужие отчёты (согласие администратора канала их НЕ покрывает)",
    "Проверка условий отдельной ленты/API/лицензии, если автор предлагает источник вне Telegram",
    "Разрешённый список каналов (allowlist) и ограниченный период первичной загрузки",
    "Политика хранения сессии (отдельный секретный файл, ограниченные права, не в git)",
    "Процесс ввода кода/2FA в защищённом интерактивном входе — не в чате и не в логах",
    "Согласование бюджета частоты запросов (Telegram rate limits) и интервала обновлений",
]

REQUIRED_APPROVALS = [
    "Product/Legal: основание использования публикаций канала (consent / license / ToS exception)",
    "Security: хранение MTProto-сессии и api_hash, ротация, доступ",
    "Data: ретеншен, право на удаление, разметка publication vs original",
    "Инженерия: allowlist каналов, checkpoint возобновления, дедупликация после рестарта",
]


@dataclass
class IncognitaConnectorConfig:
    enabled: bool = False
    api_id: int | None = None
    api_hash: str | None = None  # keep in env, never log
    session_path: str | None = None
    channel_allowlist: list[str] = field(default_factory=list)
    max_messages_per_run: int = 50
    date_from: str | None = None
    date_to: str | None = None


@dataclass
class IncognitaMessage:
    channel_id: str
    message_id: int
    date: str
    edit_date: str | None
    text: str
    urls: list[str] = field(default_factory=list)
    attachment_ids: list[str] = field(default_factory=list)
    group_id: str | None = None


class BusinessIncognitaConnector:
    """Interface + tests on synthetic fixtures only. Live calls stay disabled."""

    def __init__(self, config: IncognitaConnectorConfig):
        self.config = config

    def readiness(self) -> dict[str, Any]:
        missing = []
        if not self.config.enabled:
            missing.append("config.enabled=false")
        if not self.config.api_id or not self.config.api_hash:
            missing.append("api_id/api_hash")
        if not self.config.session_path:
            missing.append("session_path")
        if not self.config.channel_allowlist:
            missing.append("channel_allowlist")
        return {
            "status": STATUS if missing else "configured_not_legal_cleared",
            "missing": missing,
            "required_access": REQUIRED_ACCESS,
            "required_approvals": REQUIRED_APPROVALS,
            "live_enabled": bool(self.config.enabled and not missing),
        }

    async def fetch_history(self, channel: str, *, limit: int = 10) -> list[IncognitaMessage]:
        """Live MTProto getHistory — intentionally not implemented until agreement."""
        if channel not in self.config.channel_allowlist:
            raise PermissionError("channel not in allowlist")
        if not self.config.enabled:
            raise RuntimeError(STATUS)
        raise NotImplementedError(
            "Live Telegram history is blocked until requires_source_agreement is cleared"
        )

    def parse_fixture(self, payload: dict[str, Any]) -> IncognitaMessage:
        """Offline path for unit tests with synthetic messages."""
        return IncognitaMessage(
            channel_id=str(payload.get("channel_id") or "fixture"),
            message_id=int(payload.get("message_id") or 0),
            date=str(payload.get("date") or ""),
            edit_date=payload.get("edit_date"),
            text=str(payload.get("text") or ""),
            urls=list(payload.get("urls") or []),
            attachment_ids=list(payload.get("attachment_ids") or []),
            group_id=payload.get("group_id"),
        )
