"""Управляемое резервирование поиска (MIMO_TAVILY_SETUP §Управление).

Основной поставщик (по умолчанию Exa) выполняет запросы; запасной (Tavily)
вызывается только при явно включённом резервировании и недоступности основного.
Оба сервиса для одного запроса по умолчанию не запускаются.
Причина исходного сбоя сохраняется в сообщении результата (состоянии источника).
"""

from __future__ import annotations

from typing import Any

from osint_agent.market.providers.base import (
    BaseProvider,
    ProviderCapabilities,
    SearchPage,
    SourceStatus,
)

# Статусы, при которых допустимо переключение на запасной источник.
_FALLBACK_STATUSES = {
    SourceStatus.unavailable,
    SourceStatus.rate_limited,
    SourceStatus.error,
    SourceStatus.not_configured,
}


class FallbackSearchProvider(BaseProvider):
    """Основной поиск + ограниченный остаточный бюджет запасного."""

    def __init__(
        self,
        primary: BaseProvider,
        backup: BaseProvider,
        *,
        max_backup_queries: int = 2,
        budget: Any | None = None,
    ):
        self.primary = primary
        self.backup = backup
        self.max_backup_queries = max(0, int(max_backup_queries))
        self._budget = budget
        self._backup_used = 0
        self.name = primary.name

    async def capabilities(self) -> ProviderCapabilities:
        caps = await self.primary.capabilities()
        caps.notes = list(caps.notes) + [
            f"резерв: {self.backup.name} (до {self.max_backup_queries} запросов)",
        ]
        return caps

    async def aclose(self) -> None:
        await self.primary.aclose()
        await self.backup.aclose()

    def _reserve_backup(self) -> bool:
        """Остаточный бюджет запасного: по счётчику ResearchBudget либо локально."""
        if self._backup_used >= self.max_backup_queries:
            return False
        if self._budget is not None:
            consume = getattr(self._budget, "consume_backup_search", None)
            if consume is not None and not consume(1, label=f"fallback:{self.backup.name}"):
                return False
        self._backup_used += 1
        return True

    async def search_backup(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        budget: int = 10,
    ) -> SearchPage:
        """Явный дополнительный запрос запасным источником (режим «нехватка доказательств»)."""
        if not self._reserve_backup():
            return SearchPage(
                items=[],
                status=SourceStatus.empty,
                message=f"Остаточный бюджет {self.backup.name} исчерпан",
                source=self.backup.name,
                query=query,
                error_code="backup_budget_exhausted",
            )
        return await self.backup.search(query, filters=filters, cursor=cursor, budget=budget)

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        budget: int = 10,
    ) -> SearchPage:
        page = await self.primary.search(query, filters=filters, cursor=cursor, budget=budget)
        if page.status not in _FALLBACK_STATUSES:
            return page

        primary_note = f"основной {self.primary.name} → {page.status.value}"
        if page.message:
            primary_note += f": {page.message}"

        if not self._reserve_backup():
            return SearchPage(
                items=page.items,
                cursor=page.cursor,
                query=page.query or query,
                status=page.status,
                message=f"{page.message or ''} | резерв не использован (бюджет исчерпан); {primary_note}".strip(" |"),
                source=page.source,
                error_code=page.error_code,
                coverage=page.coverage,
            )

        backup_page = await self.backup.search(query, filters=filters, cursor=cursor, budget=budget)
        # Источником результатов остаётся фактический поставщик; причина переключения
        # сохраняется в сообщении — в состояниях источников видна и первопричина.
        note = f"резерв: {self.backup.name}; {primary_note}"
        if backup_page.message:
            note += f"; {backup_page.message}"
        return SearchPage(
            items=backup_page.items,
            cursor=backup_page.cursor,
            query=backup_page.query or query,
            status=backup_page.status,
            message=note,
            source=backup_page.source,
            error_code=backup_page.error_code,
            coverage=backup_page.coverage,
        )
