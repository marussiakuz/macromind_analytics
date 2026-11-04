"""Public, credential-free errors for required research services."""

import time

_SERVICE_LABELS = {
    'yandex_search': 'Поиск Yandex',
    'yandex_studio': 'Модель Yandex Studio',
    'exa_search': 'Поиск Exa',
    'tavily_search': 'Поиск Tavily',
    'local_llm': 'Локальная модель (llama-server)',
}
_REASONS = {
    'timeout': 'не ответила вовремя. Повторите исследование позже',
    'auth_error': 'отклоняет авторизацию. Проверьте ключ и права доступа на сервере',
    'not_configured': 'не настроен на сервере',
    'payment_required': 'сообщает проблему оплаты или баланса. Проверьте ключ и оплату на сервере',
    'credits_exhausted': 'исчерпал кредиты или лимит плана. Проверьте баланс на сервере',
}


class ResearchDependencyError(RuntimeError):
    def __init__(self, source: str, code: str):
        self.source = source
        self.code = code
        label = _SERVICE_LABELS.get(source, 'Источник')
        reason = _REASONS.get(code, 'недоступен')
        self.public_message = f'{label} {reason}. Новый анализ не выполнен.'
        super().__init__(self.public_message)


def _configured_search_source() -> str:
    """Идентификатор источника для выбранного поставщика поиска."""
    try:
        from osint_agent.config import settings
        provider = (settings.search_provider or '').strip().lower()
    except Exception:
        provider = ''
    return {
        'exa': 'exa_search',
        'tavily': 'tavily_search',
        'yandex': 'yandex_search',
    }.get(provider, provider or 'search')


def check_search_access(page):
    code = getattr(page, 'error_code', None)
    status = getattr(page.status, 'value', page.status)
    source = getattr(page, 'source', '') or _configured_search_source()
    # Постоянные ошибки конфигурации/доступа: сбой нового поиска не должен
    # выглядеть как сбой прежнего — источник берётся из фактического поставщика.
    if code in ('auth_error', 'not_configured', 'payment_required', 'credits_exhausted'):
        raise ResearchDependencyError(source, code)
    if status == 'not_configured':
        raise ResearchDependencyError(source, 'not_configured')


class ResearchLLM:
    """Stop on permanent configuration errors instead of retrying every research stage."""
    def __init__(self, client):
        self.client = client
        self.settings = client.settings
        self.calls = []

    def _source(self) -> str:
        if getattr(self.client, 'name', '') == 'local_llm' or type(self.client).__name__ == 'LocalLLM':
            return 'local_llm'
        return 'yandex_studio'

    async def ensure_ready(self):
        probe = getattr(self.client, 'readiness', None)
        if probe is not None:
            result = await probe()
            if not result.ok:
                raise ResearchDependencyError(self._source(), result.error_code or 'unavailable')

    async def complete(self, *args, **kwargs):
        started = time.monotonic()
        result = await self.client.complete(*args, **kwargs)
        self.calls.append({'stage': getattr(self, 'stage', 'unknown'), 'seconds': round(time.monotonic() - started, 3),
                           'ok': bool(getattr(result, 'ok', False)),
                           'prompt_tokens': getattr(result, 'prompt_tokens', 0),
                           'completion_tokens': getattr(result, 'completion_tokens', 0),
                           'error_code': getattr(result, 'error_code', None)})
        code = getattr(result, 'error_code', None)
        if code in ('auth_error', 'not_configured', 'unavailable', 'timeout'):
            raise ResearchDependencyError(self._source(), code)
        return result

    async def aclose(self):
        await self.client.aclose()
