import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchCompanyTimeline } from '../src/api/companyTimeline.js';
import {
  renderTimelineHTML,
  renderTimelineLoadingHTML,
  renderTimelineErrorHTML,
  sortNewestFirst,
  TIMELINE_COLLAPSED_COUNT,
} from '../src/render/timeline.js';

const timeline = {
  inn: '7707049388',
  name: 'ПАО Ростелеком',
  full_name: 'ПАО Ростелеком',
  entity_type: 'company',
  events: [
    { date: '2020-01-15', event: 'Изменение адреса' },
    { date: '2021-06-01', event: 'Смена руководителя' },
    { date: '2026-03-10', event: 'Новое событие' },
    { date: '2019-01-01', event: 'Старое событие' },
  ],
  source: 'checko',
};

test('fetchCompanyTimeline maps ok payload', async () => {
  let url = '';
  const res = await fetchCompanyTimeline('7707049388', {
    fetchImpl: async (u) => {
      url = u;
      return { ok: true, json: async () => ({ timeline, source: 'checko' }) };
    },
  });
  assert.match(url, /\/api\/v1\/companies\/7707049388\/timeline/);
  assert.equal(res.status, 'ok');
});

test('events sorted newest first (from end to beginning)', () => {
  const sorted = sortNewestFirst(timeline.events);
  assert.equal(sorted[0].date, '2026-03-10');
  assert.equal(sorted[1].date, '2021-06-01');
  assert.equal(sorted[sorted.length - 1].date, '2019-01-01');
});

test('timeline shows 5 newest and offers expand', () => {
  const many = {
    ...timeline,
    events: Array.from({ length: 12 }, (_, i) => ({
      date: `2026-${String(12 - i).padStart(2, '0')}-01`,
      event: `Событие ${i + 1}`,
    })),
  };
  const collapsed = renderTimelineHTML(many, false);
  assert.match(collapsed, /Событие 1/); // newest first
  assert.ok(!collapsed.includes('Событие 8')); // hidden
  assert.match(collapsed, /Развернуть ещё 7/);
  assert.match(collapsed, /timeline-toggle/);

  const expanded = renderTimelineHTML(many, true);
  assert.match(expanded, /Событие 12/);
  assert.match(expanded, /Свернуть/);
});

test('short list has no expand button', () => {
  const html = renderTimelineHTML(timeline, false);
  assert.ok(!html.includes('timeline-toggle'));
  assert.match(html, /2026/);
});

test('fetchCompanyTimeline empty list is empty not error', async () => {
  const res = await fetchCompanyTimeline('7707049388', {
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ timeline: { ...timeline, events: [] } }),
    }),
  });
  assert.equal(res.status, 'empty');
});

test('fetchCompanyTimeline validates INN and surfaces errors', async () => {
  let called = false;
  await fetchCompanyTimeline('abc', {
    fetchImpl: async () => { called = true; return { ok: true, json: async () => ({}) }; },
  });
  assert.equal(called, false);

  const err = await fetchCompanyTimeline('7707049388', {
    fetchImpl: async () => ({ ok: false, status: 502, json: async () => ({ detail: 'Сервис не ответил' }) }),
  });
  assert.equal(err.status, 'error');
  assert.match(err.message, /Сервис не ответил/);
});

test('timeline placeholders escape HTML and do not show provider name', () => {
  assert.match(renderTimelineLoadingHTML(), /историю событий/);
  const err = renderTimelineErrorHTML('boom <script>');
  assert.ok(!err.includes('<script>'));
  assert.ok(!err.includes('Checko'));
  assert.ok(!renderTimelineHTML(timeline).includes('Checko'));
});

test('TIMELINE_COLLAPSED_COUNT is 5', () => {
  assert.equal(TIMELINE_COLLAPSED_COUNT, 5);
});
