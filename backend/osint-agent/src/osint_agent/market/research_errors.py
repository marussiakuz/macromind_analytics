"""Public, credential-free errors for required research services."""


class ResearchDependencyError(RuntimeError):
    def __init__(self, source: str, code: str):
        self.source = source
        self.code = code
        label = {'yandex_search': 'Поиск Yandex', 'yandex_studio': 'Модель Yandex Studio'}.get(source, 'Источник')
        reason = {'auth_error': 'отклоняет авторизацию. Проверьте ключ и права доступа на сервере',
                  'not_configured': 'не настроен на сервере'}.get(code, 'недоступен')
        self.public_message = f'{label} {reason}. Новый анализ не выполнен.'
        super().__init__(self.public_message)


def check_search_access(page):
    code = getattr(page, 'error_code', None)
    if code in ('auth_error', 'not_configured'):
        raise ResearchDependencyError('yandex_search', code)
    if getattr(page.status, 'value', page.status) == 'not_configured':
        raise ResearchDependencyError('yandex_search', 'not_configured')


class ResearchLLM:
    """Stop on permanent configuration errors instead of retrying every research stage."""
    def __init__(self, client):
        self.client = client
        self.settings = client.settings

    async def complete(self, *args, **kwargs):
        result = await self.client.complete(*args, **kwargs)
        code = getattr(result, 'error_code', None)
        if code in ('auth_error', 'not_configured'):
            raise ResearchDependencyError('yandex_studio', code)
        return result

    async def aclose(self):
        await self.client.aclose()
