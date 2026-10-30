from types import SimpleNamespace
import pytest
from osint_agent.market.research_errors import ResearchDependencyError, ResearchLLM
from osint_agent.market.providers.base import SearchPage,SourceStatus
from osint_agent.market.universal_analysis import run_company_market_check


@pytest.mark.asyncio
async def test_search_auth_failure_stops_before_crawl_and_save(monkeypatch):
    calls=[]
    class Search:
        async def search(self,*a,**kw):
            calls.append('search')
            return SearchPage(items=[],status=SourceStatus.error,error_code='auth_error')
        async def aclose(self): calls.append('close')
    async def crawl(*a,**kw): raise AssertionError('Must not crawl after permanent auth error')
    monkeypatch.setattr('osint_agent.market.providers.web_search.YandexSearchProvider',Search)
    monkeypatch.setattr('osint_agent.market.universal_analysis.research_company_profile',crawl)
    with pytest.raises(ResearchDependencyError) as exc:
        await run_company_market_check(inn='123',company={'inn':'123','name':'Новая компания'})
    assert exc.value.source=='yandex_search'
    assert calls==['search','close']


@pytest.mark.asyncio
async def test_model_auth_failure_is_typed_and_contains_no_raw_provider_response():
    class Client:
        settings=SimpleNamespace()
        async def complete(self,*a,**kw):
            return SimpleNamespace(error_code='auth_error',error='unsafe upstream response')
    with pytest.raises(ResearchDependencyError) as exc:
        await ResearchLLM(Client()).complete('test',{})
    assert exc.value.source=='yandex_studio'
    assert 'unsafe' not in str(exc.value)
