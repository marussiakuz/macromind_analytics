"""Regression tests for the actual company → sources → interpretation → saved UI path."""
import json
from types import SimpleNamespace
import pytest
from osint_agent.market.analytical_report import validate_research_result, render_evidence_report_html, grounded_numbers
from osint_agent.market.providers.web_search import _safe_xml


def test_real_yandex_nested_passages():
    docs = _safe_xml('<response><doc><url>https://example.org</url><title>T</title><passages><passage>Производит <hlword>полимеры</hlword>.</passage><passage>Для заводов.</passage></passages></doc></response>')
    assert docs[0]['passage'] == 'Производит полимеры. Для заводов.'


def test_quote_number_and_self_competitor_guards():
    source = {'id': 'e1', 'quote': 'Тест производит полимеры. Объем рынка 42 млрд в 2024 году.'}
    good = {'text': 'Объем рынка 42 млрд в 2024 году.', 'evidence_ids': ['e1'],
            'quotes': [{'evidence_id': 'e1', 'quote': source['quote']}]}
    bad_year = dict(good, text='Объем рынка 42 млрд в 2025 году.')
    bad_quote = dict(good, quotes=[{'evidence_id': 'e1', 'quote': 'Это выдуманная цитата для отчета'}])
    comp = dict(good, name='ООО Тест', specialization='полимеры', why_competes='Полимеры для заводов')
    out = validate_research_result({'sections': {'russia': [good, bad_year, bad_quote]},
                                  'competitors': {'russia': [comp]}}, [source], 'Тест')
    assert out['sections']['russia'] == [dict(good, verification_status='needs_review')]
    assert not out['competitors']['russia']
    assert len(out['rejected']) == 3
    assert grounded_numbers('4.7 млрд', [{'quote': 'USD 4.7 billion'}])
    assert not grounded_numbers('4.7 млн', [{'quote': 'USD 4.7 billion'}])


@pytest.mark.asyncio
@pytest.mark.parametrize('product', ['полимеры для предприятий', 'автоматизация рабочих процессов'])
async def test_pipeline_persists_interpreted_sources_without_live_network(monkeypatch, tmp_path, product):
    from osint_agent.market.universal_analysis import run_company_market_check
    from osint_agent.market.repository import MarketRepository
    from osint_agent.market.providers.base import SearchPage, SourceStatus
    quote = f'Компания Тест выпускает {product}.'
    class Search:
        async def search(self, *a, **kw):
            return SearchPage(items=[{'url': 'https://example.org', 'title': 'Тест', 'passage': quote}], status=SourceStatus.ok)
        async def aclose(self): pass
    class LLM:
        settings = SimpleNamespace(max_tokens=1)
        async def complete(self, system, payload, **kwargs):
            sid = (payload.get('sources') or [{'id':'unused'}])[0]['id']
            if 'items' in payload:
                raw = {'checks': {i['id']:{'verdict':'accept','text':'','reason':''} for i in payload['items']}}
            elif 'product' in kwargs.get('json_schema', {}).get('properties', {}):
                raw = dict(product=product, product_en=product, buyers='предприятия', about=quote, evidence_ids=[sid], quote=quote)
            else:
                raw = {'sections': {'russia': [{'text': quote, 'evidence_ids': [sid], 'quotes': [{'evidence_id': sid, 'quote': quote}]}]}, 'competitors': {'russia': [], 'world': []}}
            return SimpleNamespace(ok=True, text=json.dumps(raw), model='test-model', prompt_tokens=1, completion_tokens=1, error=None)
        async def aclose(self): pass
    async def read(items, **kw): return items
    async def collect(*a, **kw): return {'evidence': [], 'source_states': []}
    monkeypatch.setattr('osint_agent.market.providers.search_factory.get_search_provider', lambda *a, **kw: Search())
    monkeypatch.setattr('osint_agent.market.providers.factory.get_llm_client', lambda *a, **kw: LLM())
    monkeypatch.setattr('osint_agent.market.universal_analysis._read_sources', read)
    monkeypatch.setattr('osint_agent.market.evidence.collect_market_evidence', collect)
    repo = MarketRepository(tmp_path / 'market.sqlite')
    result = await run_company_market_check(inn='test', company={'name':'Тест','inn':'test'}, repo=repo)
    assert result['product_scope']['product'] == product
    assert result['analytical_report']['sections']['russia'][0]['text'] == quote
    saved = repo.latest_analysis_for(legal_entity_inn='test')
    assert saved['analysis_version_id'] == result['analysis_version_id']
    assert saved['analytical_report'] == result['analytical_report']
    assert quote in saved['report_html']
    assert 'https://example.org' in saved['report_html']
    assert not result['analytical_report']['competitors']['russia']


def test_provider_uses_application_settings_when_environment_is_empty(monkeypatch):
    from pydantic import SecretStr
    from osint_agent.config import settings
    from osint_agent.market.providers.web_search import YandexSearchProvider
    from osint_agent.market.providers.openalex import OpenAlexProvider
    for key in ('YANDEX_API_KEY', 'YANDEX_FOLDER_ID', 'OPENALEX_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(settings, 'yandex_api_key', SecretStr('test-only-yandex'))
    monkeypatch.setattr(settings, 'yandex_folder_id', 'test-only-folder')
    monkeypatch.setattr(settings, 'openalex_api_key', SecretStr('test-only-openalex'))
    assert YandexSearchProvider().api_key == 'test-only-yandex'
    assert OpenAlexProvider().api_key == 'test-only-openalex'
    assert OpenAlexProvider(api_key='').api_key == ''


@pytest.mark.asyncio
async def test_evidence_audit_drops_unsupported_competitor_and_repairs_geography():
    from osint_agent.market.analytical_report import audit_report
    class LLM:
        async def complete(self, system, payload, **kwargs):
            assert payload['as_of']
            return SimpleNamespace(ok=True, text=json.dumps({'checks':{'C1': ({'verdict':'revise','text':'В мире доля составляет 1,5%.','reason':''} if payload['items'][0]['kind']=='sections' else {'verdict':'reject','text':'','reason':'Совпадает отрасль, но не продукт'})}}),
                prompt_tokens=1, completion_tokens=1, error=None)
    report={'sections':{'trends':[{'text':'В России доля составляет 1,5%.','quotes':[{'quote':'В мире доля составляет 1,5%.'}]}]},
            'competitors':{'russia':[{'name':'Не тот продукт','quotes':[{'quote':'Другая специализация производителя'}]}]},'rejected':[]}
    out=await audit_report(report,{'product':'реакторы'},LLM())
    assert out['sections']['trends'][0]['text']=='В мире доля составляет 1,5%.'
    assert out['competitors']['russia']==[]
    assert out['audit_status']=='completed'


def test_financial_context_preserves_known_revenue_and_questions_use_segment_gap():
    from osint_agent.market.analytical_report import financial_context, reconcile_financial_questions
    summary = {'finance_summary':{'latest_year':{'year':2025,'revenue':347351000}},
               'finances':{'years':[{'year':2025,'revenue':347351000}]}}
    assert financial_context(summary)['latest_year']['revenue'] == 347351000
    question = reconcile_financial_questions(['Требуется информация о выручке компании'], summary)[0]
    assert '347 351 000' in question
    assert 'часть' in question
    assert 'Требуется информация о выручке' not in question
    assert reconcile_financial_questions(['Укажите выручку'], {}) == ['Укажите выручку']


def test_equipment_vendors_do_not_require_a_branded_product():
    sources = [{'id':'a','quote':'Завод Альфа производит гидроцилиндры для строительных машин.'},
               {'id':'b','quote':'Завод Бета производит гидроцилиндры для строительных машин.'}]
    rows = [{'name':name,'product_name':'','specialization':'Гидроцилиндры',
             'why_competes':'Гидроцилиндры для строительных машин','evidence_ids':[src['id']],
             'quotes':[{'evidence_id':src['id'],'quote':src['quote']}]} for name,src in zip(['Завод Альфа','Завод Бета'],sources)]
    result = validate_research_result({'competitors':{'russia':rows}}, sources, 'Другая компания')
    assert len(result['competitors']['russia']) == 2


@pytest.mark.asyncio
async def test_candidate_discovery_searches_product_pages_and_ignores_invented_names(monkeypatch):
    from osint_agent.market.universal_analysis import _collect_competitor_product_pages
    from osint_agent.market.providers.base import SearchPage, SourceStatus
    calls = []
    class Search:
        async def search(self, query, **kwargs):
            calls.append((query, kwargs['filters']['region']))
            return SearchPage(items=[{'url':'https://vendor.example/products','title':'Завод Альфа',
                                     'passage':'Завод Альфа выпускает насосы для машин.'}], status=SourceStatus.ok)
        async def aclose(self): pass
    class LLM:
        async def complete(self, system, payload, **kwargs):
            sid = payload['sources'][0]['id']
            return SimpleNamespace(ok=True, text=json.dumps({'russia':[
                {'name':'Завод Альфа','product':'насосы','evidence_id':sid},
                {'name':'Выдуманный завод','product':'насосы','evidence_id':sid}], 'world':[]}),error=None)
    async def read(rows, **kwargs): return rows
    monkeypatch.setattr('osint_agent.market.providers.search_factory.get_search_provider', lambda *a, **kw: Search())
    monkeypatch.setattr('osint_agent.market.universal_analysis._read_sources', read)
    rows, states = await _collect_competitor_product_pages({'product':'насосы'}, [
        {'id':'s','title':'Каталог','url':'https://catalog.example',
         'quote':'Завод Альфа производит насосы для строительных машин.'}], LLM())
    assert len(calls) == 1
    assert calls[0][1] == 'RU'
    assert 'Завод Альфа' in calls[0][0] and 'насосы' in calls[0][0]
    assert rows[0]['competitor_candidate'] == 'Завод Альфа'
    assert states[0]['count'] == 1
