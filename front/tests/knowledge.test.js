import assert from 'node:assert/strict';
import test from 'node:test';
import {
  knowledgeSearch,
  listKnowledgeSignals,
  knowledgeBridgeMarket,
} from '../src/api/knowledge.js';
import {
  renderEvidenceSourcesHTML,
  renderKnowledgeSignalsHTML,
  renderKnowledgeSearchResultsHTML,
} from '../src/render/knowledge.js';
import { renderMarketSummaryHTML, renderMarketDetailHTML } from '../src/render/market.js';
import { marketState, resetMarketState } from '../src/market/state.js';

test('knowledgeSearch posts question and returns retrieval shape', async () => {
  let url = '';
  let body = null;
  const res = await knowledgeSearch(
    { question: 'объем рынка RPA', mode: 'hybrid' },
    {
      fetchImpl: async (u, opts) => {
        url = u;
        body = JSON.parse(opts.body);
        return {
          ok: true,
          json: async () => ({
            retrieval_id: 'r-1',
            mode: 'hybrid',
            items: [],
            limitations: [],
            empty_reason: 'no_evidence_in_allowed_corpus',
          }),
          text: async () => JSON.stringify({
            retrieval_id: 'r-1',
            mode: 'hybrid',
            items: [],
            limitations: [],
            empty_reason: 'no_evidence_in_allowed_corpus',
          }),
        };
      },
    },
  );
  assert.match(url, /\/api\/v1\/knowledge\/search$/);
  assert.equal(body.question, 'объем рынка RPA');
  assert.equal(res.empty_reason, 'no_evidence_in_allowed_corpus');
});

test('listKnowledgeSignals hits signals endpoint', async () => {
  let url = '';
  const res = await listKnowledgeSignals(
    { workspace_id: 'ws-1' },
    {
      fetchImpl: async (u) => {
        url = u;
        return {
          ok: true,
          text: async () => JSON.stringify({ events: [], hypotheses: [] }),
        };
      },
    },
  );
  assert.match(url, /\/api\/v1\/knowledge\/signals/);
  assert.deepEqual(res.events, []);
});

test('knowledgeBridgeMarket posts summary', async () => {
  let body = null;
  await knowledgeBridgeMarket(
    { company: { name: 'X' } },
    { workspace_id: 'ws' },
    {
      fetchImpl: async (u, opts) => {
        body = JSON.parse(opts.body);
        return { ok: true, text: async () => '{"entity_id":"e1","evidence_stored":1}' };
      },
    },
  );
  assert.equal(body.summary.company.name, 'X');
  assert.equal(body.workspace_id, 'ws');
});

test('renderEvidenceSourcesHTML shows verification and snippet completeness', () => {
  const html = renderEvidenceSourcesHTML([
    {
      id: 'yandex:1',
      title: 'Рынок RPA',
      url: 'https://example.org',
      quote: '12 млрд',
      claim_type: 'unverified_snippet',
      verification_status: 'unreviewed',
      completeness: 'snippet_only',
      source_id: 'yandex_search',
    },
  ]);
  assert.match(html, /Рынок RPA/);
  assert.match(html, /не проверено/);
  assert.match(html, /фрагмент|только выдержка/);
  assert.match(html, /yandex_search/);
});

test('renderEvidenceSourcesHTML empty state has reason text', () => {
  const html = renderEvidenceSourcesHTML([], { emptyText: 'Внешние источники ещё не подключены.' });
  assert.match(html, /Внешние источники ещё не подключены/);
});

test('renderKnowledgeSignalsHTML shows independent sources and hypothesis limits', () => {
  const html = renderKnowledgeSignalsHTML({
    events: [{
      event_type: 'product_launch',
      subject: 'Запуск платформы',
      independent_sources: 1,
      event_at: '2026-10-01',
    }],
    hypotheses: [{
      statement: 'Появились испытания',
      status: 'needs_more_data',
      limitations: ['Базовое количество равно нулю'],
      coverage_limited: true,
    }],
  });
  assert.match(html, /Запуск платформы/);
  assert.match(html, /независимых источников/);
  assert.match(html, /Базовое количество равно нулю/);
  assert.match(html, /Сравнение периодов ограничено/);
});

test('renderKnowledgeSignalsHTML loading and error states', () => {
  assert.match(renderKnowledgeSignalsHTML({ loading: true }), /Загрузка событий/);
  assert.match(renderKnowledgeSignalsHTML({ error: 'down' }), /down/);
});

test('renderKnowledgeSearchResultsHTML empty corpus is normal result', () => {
  const html = renderKnowledgeSearchResultsHTML({
    items: [],
    empty_reason: 'no_evidence_in_allowed_corpus',
    limitations: ['embedding_service_unavailable'],
  });
  assert.match(html, /нет подходящих доказательств/);
  assert.match(html, /embedding_service_unavailable/);
});

test('market summary embeds evidence sources and LLM as interpretation', () => {
  const html = renderMarketSummaryHTML({
    market_scope: { product: 'RPA' },
    evidence_refs: [{
      id: 'y:1',
      title: 'Отчет',
      quote: 'текст',
      claim_type: 'unverified_snippet',
      verification_status: 'unreviewed',
    }],
    llm_interpretation: [{ text: 'Рынок растет' }],
    limitations: [],
  });
  assert.match(html, /Источники выводов/);
  assert.match(html, /Интерпретация \(не факт\)/);
  assert.match(html, /Рынок растет/);
  assert.match(html, /не проверено/);
});

test('market detail has knowledge search form and empty corpus result', () => {
  resetMarketState();
  marketState.detailOpen = true;
  marketState.summary = { evidence_refs: [], competitor_findings: [] };
  marketState.knowledgeQuery = 'поставщики RPA';
  marketState.knowledgeResult = {
    items: [],
    empty_reason: 'no_evidence_in_allowed_corpus',
    limitations: [],
  };
  const html = renderMarketDetailHTML();
  assert.match(html, /market-knowledge-search-form/);
  assert.match(html, /Поиск доказательств/);
  assert.match(html, /нет подходящих доказательств/);
  resetMarketState();
});

test('market detail knowledge search shows loading state', () => {
  resetMarketState();
  marketState.detailOpen = true;
  marketState.summary = {};
  marketState.knowledgeLoading = true;
  const html = renderMarketDetailHTML();
  assert.match(html, /Поиск по базе знаний/);
  resetMarketState();
});
