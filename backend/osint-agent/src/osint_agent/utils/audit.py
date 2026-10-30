"""Audit logging for external API requests (152-ФЗ compliance).

ВАЖНО: Для 152-ФЗ compliance аудит-лог ДОЛЖЕН быть персистентным.
При перезапуске приложения записи не должны теряться.

Реализация:
- Основное хранение: JSON Lines файл (для MVP)
- Production: PostgreSQL (реализовать позже)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from osint_agent.utils import get_logger

logger = get_logger(__name__)

# Путь к файлу аудит-лога (по умолчанию в data/audit/)
DEFAULT_AUDIT_DIR = Path("data/audit")


class AuditEntry(BaseModel):
    """Audit log entry for external API request."""
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    tenant_id: str | None = None
    connector_name: str
    query_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    success: bool
    source: str
    error: str | None = None
    duration_ms: float = 0.0


class AuditLog:
    """Audit log for external API requests.

    Хранение:
    - В памяти (для быстрого доступа)
    - В JSON Lines файле (для персистентности)
    - В PostgreSQL (для production, TODO)
    """

    def __init__(self, audit_dir: Path | str | None = None):
        self._entries: list[AuditEntry] = []
        self._audit_dir = Path(audit_dir) if audit_dir else DEFAULT_AUDIT_DIR
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._current_file: Path | None = None

    def _get_audit_file(self) -> Path:
        """Получить текущий файл аудит-лога (по датам)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return self._audit_dir / f"audit_{today}.jsonl"

    async def log(
        self,
        connector_name: str,
        query_type: str,
        params: dict[str, Any],
        success: bool,
        source: str,
        error: str | None = None,
        duration_ms: float = 0.0,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> AuditEntry:
        """Log an external API request.

        152-ФЗ: Каждый доступ к персональным данным ДОЛЖЕН быть залогирован.
        """
        entry = AuditEntry(
            connector_name=connector_name,
            query_type=query_type,
            params=params,
            success=success,
            source=source,
            error=error,
            duration_ms=duration_ms,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        # Сохраняем в память
        self._entries.append(entry)

        # Сохраняем в файл (персистентность)
        await self._persist_to_file(entry)

        return entry

    async def _persist_to_file(self, entry: AuditEntry) -> None:
        """Сохранить запись в JSON Lines файл."""
        try:
            audit_file = self._get_audit_file()
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            # Не падаем из-за ошибки логирования
            logger.error("audit_file_write_error", error=str(e))

    async def get_entries(
        self,
        connector_name: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Get audit log entries from memory."""
        entries = self._entries
        if connector_name:
            entries = [e for e in entries if e.connector_name == connector_name]
        return entries[-limit:]

    async def get_entries_from_file(
        self,
        date: str | None = None,
        connector_name: str | None = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """Get audit log entries from file (for historical data).

        Args:
            date: Дата в формате YYYY-MM-DD (по умолчанию — сегодня)
            connector_name: Фильтр по коннектору
            limit: Максимальное количество записей
        """
        if date:
            audit_file = self._audit_dir / f"audit_{date}.jsonl"
        else:
            audit_file = self._get_audit_file()

        if not audit_file.exists():
            return []

        entries = []
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = AuditEntry.model_validate_json(line)
                        if connector_name and entry.connector_name != connector_name:
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.error("audit_file_read_error", error=str(e))

        return entries


# Global instance
audit_log = AuditLog()
