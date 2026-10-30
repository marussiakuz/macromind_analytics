import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchCompanyFinances } from '../src/api/companyFinances.js';
import {
  renderFinanceChart,
  renderFinancesHTML,
  renderFinancesErrorHTML,
} from '../src/render/finances.js';

const finances = {
  inn: '7707049388',
  ogrn: '1027700198767',
  name: 'ПАО Ростелеком',
  full_name: 'ПАО Ростелеком',
  entity_type: 'company',
  years: [
    { year: 2021, revenue: 550000000000, net_profit: 30000000000 },
    { year: 2022, revenue: 590000000000, net_profit: -1000000000 },
    { year: 2023, revenue: 640000000000, net_profit: 22000000000 },
  ],
  report_links: { 2023: 'https://bo.nalog.gov.ru/1.pdf', 2022: 'https://bo.nalog.gov.ru/2.pdf' },
  source: 'checko',
};

test('fetchCompanyFinances maps ok payload', async () => {
  let url = '';
  const res = await fetchCompanyFinances('7707049388', {
    fetchImpl: async (u) => {
      url = u;
      return { ok: true, json: async () => ({ finances, source: 'checko' }) };
    },
  });
  assert.match(url, /\/api\/v1\/companies\/7707049388\/finances/);
  assert.equal(res.status, 'ok');
  assert.equal(res.finances.years.length, 3);
});

test('fetchCompanyFinances skips non-company INN without request', async () => {
  let called = false;
  const res = await fetchCompanyFinances('770303580308', {
    fetchImpl: async () => { called = true; return { ok: true, json: async () => ({}) }; },
  });
  assert.equal(res.status, 'skipped');
  assert.equal(called, false);
});

test('fetchCompanyFinances reports empty and error', async () => {
  const empty = await fetchCompanyFinances('7707049388', {
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        finances: { ...finances, years: [{ year: 2020, revenue: null, net_profit: null }] },
      }),
    }),
  });
  assert.equal(empty.status, 'empty');

  const err = await fetchCompanyFinances('7707049388', {
    fetchImpl: async () => ({ ok: false, status: 502, json: async () => ({ detail: 'Checko не ответил' }) }),
  });
  assert.equal(err.status, 'error');
  assert.match(err.message, /Checko не ответил/);
});

test('finances card renders summary, two charts and table', () => {
  const html = renderFinancesHTML(finances);
  assert.match(html, /Финансовая отчетность/);
  assert.match(html, /Выручка компании/);
  assert.match(html, /Чистая прибыль/);
  assert.match(html, /640\.0 млрд/);
  assert.match(html, /2023/);
  assert.match(html, /bo\.nalog\.gov\.ru/);
});

test('chart renders bars and escapes title', () => {
  const svg = renderFinanceChart(
    [{ year: 2021, value: 100 }, { year: 2022, value: -50 }],
    { title: 'Выручка <x>' },
  );
  assert.match(svg, /<rect/);
  assert.match(svg, /2021/);
  assert.match(svg, /role="img"/);
  assert.ok(!svg.includes('<x>'));
});

test('error placeholder escapes message', () => {
  const html = renderFinancesErrorHTML('boom <script>');
  assert.ok(!html.includes('<script>'));
  assert.match(html, /Финансовая отчетность/);
});
