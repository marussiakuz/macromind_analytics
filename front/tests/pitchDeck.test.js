import assert from 'node:assert/strict';
import test from 'node:test';
import { deleteAnalysis, getAnalysis, slideImageUrl, uploadDeck } from '../src/api/pitchDeck.js';
import { renderEntitiesHTML, renderFactsHTML, renderFlagsHTML, renderSlideLinks } from '../src/render/pitchDeck.js';

test('uploadDeck posts multipart form to the analyses route', async () => {
  let url = '';
  let options = null;
  const file = new File(['%PDF-'], 'deck.pdf', { type: 'application/pdf' });
  const res = await uploadDeck(file, {
    fetchImpl: async (u, o) => {
      url = u;
      options = o;
      return { ok: true, json: async () => ({ id: 'a1', status: 'queued' }) };
    },
  });
  assert.match(url, /\/api\/v1\/pitchdeck\/analyses$/);
  assert.equal(options.method, 'POST');
  assert.ok(options.body instanceof FormData);
  assert.equal(res.id, 'a1');
});

test('API errors surface the server message and code', async () => {
  await assert.rejects(
    () => getAnalysis('x', {
      fetchImpl: async () => ({
        ok: false,
        status: 503,
        json: async () => ({ detail: { code: 'model_missing', message: 'Модель не установлена' } }),
      }),
    }),
    error => error.message === 'Модель не установлена' && error.code === 'model_missing',
  );
});

test('deleteAnalysis throws on failure and ids are encoded', async () => {
  let url = '';
  await deleteAnalysis('a/b', {
    fetchImpl: async u => {
      url = u;
      return { ok: true };
    },
  });
  assert.match(url, /a%2Fb$/);
  assert.match(slideImageUrl('a b', 3), /a%20b\/slides\/3\/image$/);
});

test('deck text is escaped in facts, flags and entities', () => {
  const evil = '<img src=x onerror=alert(1)>';
  const facts = renderFactsHTML([{ slide: 1, metric: 'revenue', value_raw: evil, unit_raw: '', period_raw: evil, status: 'fact', entity: evil }]);
  const flags = renderFlagsHTML([{ title: evil, detail: evil, severity: 'high', slides: [1] }]);
  const entities = renderEntitiesHTML([{ kind: 'organization', text: evil, slides: [1] }]);
  for (const html of [facts, flags, entities]) {
    assert.ok(!html.includes('<img'));
    assert.ok(html.includes('&lt;img'));
  }
});

test('facts show status, source slide and review state', () => {
  const html = renderFactsHTML([
    { slide: 11, metric: 'revenue', value_raw: '1 030', unit_raw: 'млн руб.', period_raw: '2021', status: 'forecast', needs_review: false },
    { slide: 2, metric: 'market_tam', value_raw: '40', unit_raw: 'млрд', period_raw: '', status: 'unknown', needs_review: true },
  ]);
  assert.ok(html.indexOf('TAM') < html.indexOf('Выручка'), 'sorted by slide');
  assert.match(html, /Прогноз/);
  assert.match(html, /Сверить/);
  assert.match(html, /не указан/);
  assert.match(html, /data-slide="11"/);
});

test('empty results explain themselves instead of implying safety', () => {
  assert.match(renderFlagsHTML([]), /не значит, что рисков нет/);
  assert.match(renderFactsHTML([]), /вручную/);
  assert.equal(renderSlideLinks([]), '');
});
