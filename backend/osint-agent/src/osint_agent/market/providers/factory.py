"""Unified LLM client factory (MIMO Market Recovery §3).

Returns YandexStudioLLM or LocalLLM based on settings.llm_provider.
All creation points must go through this factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from osint_agent.market.providers.yandex_llm import YandexStudioLLM
    from osint_agent.market.providers.local_llm import LocalLLM


def get_llm_client() -> "YandexStudioLLM | LocalLLM":
    """Return the configured LLM client. One way for all callers."""
    from osint_agent.config import settings

    provider = (settings.llm_provider or "yandex").lower()

    if provider == "local":
        from osint_agent.market.providers.local_llm import LocalLLM, load_local_llm_settings

        return LocalLLM(settings=load_local_llm_settings())

    # default: yandex
    from osint_agent.market.providers.yandex_llm import YandexStudioLLM

    return YandexStudioLLM()
