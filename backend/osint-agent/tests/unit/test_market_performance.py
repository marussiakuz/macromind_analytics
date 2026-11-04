"""Fail early on dependency failures; do not silently save empty market reports."""
import httpx
import pytest
from types import SimpleNamespace
from osint_agent.market.providers.local_llm import LocalLLM, LocalLLMSettings
from osint_agent.market.research_errors import ResearchDependencyError, ResearchLLM


@pytest.mark.asyncio
async def test_readiness_is_short_health_probe_not_generation():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'status': 'ok'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        model = LocalLLM(LocalLLMSettings(base_url='http://model:8080/v1'), client=client)
        assert (await model.readiness()).ok
    assert [(r.method, r.url.path) for r in requests] == [('GET', '/health')]
    assert requests[0].extensions['timeout']['read'] == 5.0


@pytest.mark.asyncio
async def test_unavailable_model_stops_before_search_and_save(monkeypatch):
    from osint_agent.market.universal_analysis import run_company_market_check
    closed = []
    class Client:
        name = 'local_llm'
        settings = SimpleNamespace()
        async def readiness(self):
            return SimpleNamespace(ok=False, error_code='unavailable')
        async def aclose(self): closed.append(True)
    def no_search(**kwargs):
        raise AssertionError('Must not search when model is unavailable')
    class Repo:
        def save_analysis_version(self, *args, **kwargs):
            raise AssertionError('Must not persist service failure as report')
    monkeypatch.setattr('osint_agent.market.providers.factory.get_llm_client', lambda: Client())
    monkeypatch.setattr('osint_agent.market.providers.search_factory.get_search_provider', no_search)
    with pytest.raises(ResearchDependencyError, match='Локальная модель'):
        await run_company_market_check(inn='123', company={'name': 'Тест'}, repo=Repo())
    assert closed == [True]


@pytest.mark.asyncio
async def test_runtime_timeout_is_typed_and_measured():
    class Client:
        name = 'local_llm'
        settings = SimpleNamespace()
        async def complete(self, *args, **kwargs):
            return SimpleNamespace(ok=False, error_code='timeout', prompt_tokens=12, completion_tokens=0)
    llm = ResearchLLM(Client())
    with pytest.raises(ResearchDependencyError) as exc:
        await llm.complete('test', {})
    assert exc.value.code == 'timeout'
    assert llm.calls[0]['seconds'] >= 0
    assert llm.calls[0]['prompt_tokens'] == 12
