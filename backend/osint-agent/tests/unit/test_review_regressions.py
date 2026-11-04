"""Regression checks for shared budgets and preservation of report evidence."""
import json
from types import SimpleNamespace

import pytest

from osint_agent.market.research_budget import ResearchBudget
from osint_agent.market.providers.base import SearchPage, SourceStatus


def test_backup_obeys_total_budget_and_deadline():
    budget = ResearchBudget(max_search_queries=1)
    assert budget.consume_search() == 1
    assert budget.consume_backup_search() == 0
    assert budget.used_search == 1
    expired = ResearchBudget(max_seconds=0)
    assert expired.consume_backup_search() == 0
    assert expired.consume_search() == 0
    assert expired.consume_reads() == 0


@pytest.mark.asyncio
async def test_stage_b_uses_remaining_budget_once(monkeypatch):
    from osint_agent.market.competitor_research import discover_direction_candidates
    calls = []

    class Search:
        async def search(self, query, **kwargs):
            calls.append(query)
            return SearchPage(items=[], status=SourceStatus.empty)

        async def aclose(self):
            pass

    monkeypatch.setattr('osint_agent.market.providers.search_factory.get_search_provider', lambda **kw: Search())
    budget = ResearchBudget()
    budget.consume_search(10)
    await discover_direction_candidates(
        {'name': 'Тест'},
        [{'direction_id': 'd1', 'product_category_ru': 'датчики', 'product_category_en': 'sensors'}],
        query_budget=budget.max_search_queries - budget.used_search, budget=budget,
    )
    assert calls
    assert budget.used_search == 10 + len(calls)


@pytest.mark.asyncio
async def test_supplement_respects_search_and_read_budget(monkeypatch):
    from osint_agent.market.universal_analysis import _collect_competitor_product_pages
    calls, read_limits = [], []

    class Search:
        async def search(self, query, **kwargs):
            calls.append(query)
            return SearchPage(items=[{'url': 'https://example.org/product', 'passage': 'Производство датчиков'}],
                              status=SourceStatus.ok)

        async def aclose(self):
            pass

    class LLM:
        async def complete(self, system, payload, **kwargs):
            sid = payload['sources'][0]['id']
            return SimpleNamespace(ok=True, text=json.dumps({'russia': [
                {'name': name, 'product': 'датчики', 'evidence_id': sid} for name in ('Альфа', 'Бета')], 'world': []}))

    async def read(rows, limit):
        read_limits.append(limit)
        return rows

    monkeypatch.setattr('osint_agent.market.providers.search_factory.get_search_provider', lambda **kw: Search())
    monkeypatch.setattr('osint_agent.market.universal_analysis._read_sources', read)
    budget = ResearchBudget(max_search_queries=1, max_document_reads=0)
    _, states = await _collect_competitor_product_pages({}, [
        {'id': 'e1', 'quote': 'Альфа и Бета производят датчики.', 'url': 'https://example.org'}], LLM(), budget=budget)
    assert len(calls) == 1
    assert budget.used_search == 1
    assert read_limits == [0]
    assert any(s['status'] == 'not_executed' for s in states)


@pytest.mark.asyncio
async def test_audit_keeps_tail_of_citation_and_reports_partial_failure():
    from osint_agent.market.analytical_report import _audit_batch
    quote = 'Описание продукции. ' * 50 + ' Объем рынка 17 млрд рублей.'
    seen = []

    class LLM:
        async def complete(self, system, payload, **kwargs):
            seen.extend(payload['items'])
            if len(seen) > 4:
                return SimpleNamespace(ok=False, text='', error='timeout', prompt_tokens=0, completion_tokens=0)
            return SimpleNamespace(ok=True, text=json.dumps({'checks': {
                i['id']: {'verdict': 'accept', 'text': '', 'reason': ''} for i in payload['items']}}),
                prompt_tokens=1, completion_tokens=1)

    row = {'text': 'Объем рынка 17 млрд рублей.', 'evidence_ids': ['e1'],
           'quotes': [{'evidence_id': 'e1', 'quote': quote}]}
    report = {'sections': {'russia': [dict(row) for _ in range(5)]}, 'competitors': {}, 'rejected': []}
    out = await _audit_batch(report, {}, LLM())
    assert seen[0]['evidence'] == [quote]
    assert out['audit_status'] == 'partial'
    assert out['error'] == 'timeout'
    assert len(out['sections']['russia']) == 4


@pytest.mark.asyncio
async def test_audit_missing_verdict_is_partial():
    from osint_agent.market.analytical_report import _audit_batch

    class LLM:
        async def complete(self, *args, **kwargs):
            return SimpleNamespace(ok=True, text='{"checks":{}}', prompt_tokens=0, completion_tokens=0)

    report = {'sections': {'russia': [{'text': 'Текст', 'quotes': []}]}, 'competitors': {}, 'rejected': []}
    result = await _audit_batch(report, {}, LLM())
    assert result['audit_status'] == 'partial'
    assert 'C1' in result['error']


@pytest.mark.asyncio
async def test_interpretation_preserves_numeric_evidence_after_character_800(monkeypatch):
    from osint_agent.market.analytical_report import interpret_market_report
    quote = 'Описание продукции. ' * 45 + ' Объем рынка 17 млрд рублей.'

    class LLM:
        async def complete(self, system, payload, **kwargs):
            if 'items' in payload:
                data = {'checks': {i['id']: {'verdict': 'accept', 'text': '', 'reason': ''}
                                   for i in payload['items']}}
            else:
                data = {'sections': {'russia': [{'text': 'Объем рынка 17 млрд рублей.',
                                                'evidence_ids': ['P1']}]},
                        'competitors': {'russia': [], 'world': []}, 'questions': []}
            return SimpleNamespace(ok=True, text=json.dumps(data), model='test', error=None,
                                   prompt_tokens=1, completion_tokens=1)

    result = await interpret_market_report(
        {'company_name': 'Тест', 'product_scope': {'product': 'продукция'}},
        [{'id': 'e1', 'quote': quote, 'title': 'Обзор', 'url': 'https://example.org',
          'read_level': 'page_excerpt'}], LLM())
    assert result['sections']['russia'][0]['quotes'][0]['quote'] == quote


def test_fallback_setting_still_applies_with_shared_budget():
    from osint_agent.market.providers.search_fallback import FallbackSearchProvider
    budget = ResearchBudget(max_backup_search=2)
    provider = FallbackSearchProvider(SimpleNamespace(name='primary'), SimpleNamespace(name='backup'),
                                      max_backup_queries=1, budget=budget)
    assert provider._reserve_backup()
    assert not provider._reserve_backup()
    assert budget.used_search == 1
