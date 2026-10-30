import assert from 'node:assert/strict';
import test from 'node:test';
import {
  allTrends,
  excludedItems,
  searchStats,
  trendById,
  trendTrust,
  filterTrendsByQuery,
} from '../src/data/weakSignals.js';

test('weak signals data has trends, stats and excluded items', () => {
  assert.ok(allTrends.length >= 10);
  assert.ok(excludedItems.length >= 5);
  assert.ok(searchStats.candidates > 0);
  assert.ok(searchStats.sources > 0);
  assert.ok(searchStats.highConfidence > 0);
});

test('trend lookup and trust helper work', () => {
  const first = allTrends[0];
  const found = trendById(first.id);
  assert.equal(found.id, first.id);
  assert.ok(['высокий', 'средний', 'низкий'].includes(trendTrust(first)));
  assert.ok(first.name && first.definition && first.signal != null);
  assert.ok(Array.isArray(first.sources) && first.sources.length > 0);
});

test('filter does not return unrelated cards for nano-robotics', () => {
  const res = filterTrendsByQuery('нано технологии в робототехнике');
  assert.equal(res.length, 0);
});

test('filter matches topic keywords', () => {
  const citata = filterTrendsByQuery('цитат');
  assert.ok(citata.length >= 1);
  assert.ok(citata.some(t => /цитат/i.test(t.name + t.definition)));
  const conf = filterTrendsByQuery('конфиденциальный инференс');
  assert.equal(conf.length, 1);
  assert.match(conf[0].name, /Конфиденциальный/);
});

test('AI query returns related AI trends not arbitrary list', () => {
  const ai = filterTrendsByQuery('технологии в ИИ');
  assert.ok(ai.length >= 3);
  assert.ok(ai.length < allTrends.length);
});
