"""Unified search client factory (MIMO_EXA_SETUP / MIMO_TAVILY_SETUP).

Возвращает поставщика по settings.search_provider: exa | tavily | yandex.
Неизвестное имя — понятная ошибка настройки; молчаливого запуска Yandex нет.
При явно включённом settings.search_fallback основной поставщик оборачивается
управляемым резервированием (FallbackSearchProvider).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from osint_agent.market.providers.base import BaseProvider

KNOWN_PROVIDERS = ("exa", "tavily", "yandex")


def _build_primary(provider: str) -> "BaseProvider":
    if provider == "exa":
        from osint_agent.market.providers.exa_search import ExaSearchProvider

        return ExaSearchProvider()
    if provider == "tavily":
        from osint_agent.market.providers.tavily_search import TavilySearchProvider

        return TavilySearchProvider()
    if provider == "yandex":
        from osint_agent.market.providers.web_search import YandexSearchProvider

        return YandexSearchProvider()
    raise ValueError(
        f"Неизвестный поставщик поиска: {provider!r}. Допустимо: {', '.join(KNOWN_PROVIDERS)}"
    )


def get_search_provider(budget: Any | None = None) -> "BaseProvider":
    """Return the configured search provider. One way for all callers."""
    from osint_agent.config import settings

    provider = (settings.search_provider or "").strip().lower()
    if not provider:
        raise ValueError(
            f"search_provider не задан. Допустимо: {', '.join(KNOWN_PROVIDERS)}"
        )

    primary = _build_primary(provider)

    if not settings.search_fallback:
        return primary

    from osint_agent.market.providers.search_fallback import FallbackSearchProvider

    backup_name = (settings.search_fallback_provider or "tavily").strip().lower()
    if backup_name == provider:
        return primary
    backup = _build_primary(backup_name)
    return FallbackSearchProvider(
        primary,
        backup,
        max_backup_queries=settings.search_fallback_budget,
        budget=budget,
    )
