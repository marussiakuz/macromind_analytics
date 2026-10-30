import assert from 'node:assert/strict';
import test from 'node:test';
import {
  detectSearchType,
  normalizeSearchQuery,
  validateSearchQuery,
  searchCompanies,
} from '../src/api/companySearch.js';

function makeFetch(capture) {
  return async (url) => {
    capture.push(url);
    return {
      ok: true,
      json: async () => ({
        results: [{ inn: '7707083893', name: 'ПАО СБЕРБАНК' }],
        total_pages: 3,
        page: 1,
        source: 'checko',
        balance: 0,
        today_request_count: 41,
      }),
    };
  };
}

test('OKVED codes of every level are detected as okved', () => {
  for (const code of ['62', '62.0', '62.01', '62.01.1', '62.01.11']) {
    assert.equal(detectSearchType(code), 'okved', code);
  }
});

test('name and date keep correct types', () => {
  assert.equal(detectSearchType('пао ростелеком'), 'name');
  assert.equal(detectSearchType('2020-12-31'), 'reg-date');
  assert.equal(detectSearchType('founder: нуралиев борис'), 'founder-name');
  assert.equal(detectSearchType('leader: греф герман'), 'leader-name');
});

test('min length 4 only for name-like searches', () => {
  assert.match(validateSearchQuery('abc', 'name') || '', /4 символа/);
  assert.equal(validateSearchQuery('62', 'okved'), null);
  assert.equal(validateSearchQuery('62.01.1', 'okved'), null);
  assert.equal(validateSearchQuery('', 'name') != null, true);
});

test('short okved is sent as by=okved without local 3-char reject', async () => {
  const urls = [];
  const data = await searchCompanies('62', {
    fetchImpl: makeFetch(urls),
  });
  assert.equal(data.by, 'okved');
  assert.match(urls[0], /by=okved/);
  assert.match(urls[0], /q=62/);
  assert.match(urls[0], /page=1/);
});

test('62.01.1 goes to okved not name', async () => {
  const urls = [];
  await searchCompanies('62.01.1', { fetchImpl: makeFetch(urls) });
  assert.match(urls[0], /by=okved/);
  assert.ok(!urls[0].includes('by=name'));
  assert.match(urls[0], /q=62\.01\.1/);
});

test('founder and leader prefixes stripped from query', async () => {
  const urls = [];
  await searchCompanies('founder: Иванов', { fetchImpl: makeFetch(urls) });
  assert.match(urls[0], /by=founder-name/);
  assert.match(urls[0], /q=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2/); // Иванов
  assert.ok(!urls[0].includes('founder:') && !urls[0].includes('founder%3A'));
});

test('name search keeps query and uses by=name', async () => {
  const urls = [];
  await searchCompanies('пао ростелеком', { fetchImpl: makeFetch(urls) });
  assert.match(urls[0], /by=name/);
  assert.match(urls[0], /q=%D0%BF%D0%B0%D0%BE\+|%D1%80%D0%BE%D1%81%D1%82%D0%B5%D0%BB%D0%B5%D0%BA%D0%BE%D0%BC/);
  assert.ok(urls[0].includes('D1%80%D0%BE%D1%81%D1%82%D0%B5%D0%BB%D0%B5%D0%BA%D0%BE%D0%BC')); // ростелеком
});

test('explicit type override wins over auto-detect', async () => {
  const urls = [];
  await searchCompanies('62.01', {
    fetchImpl: makeFetch(urls),
    searchTypeOverride: 'name',
  });
  assert.match(urls[0], /by=name/);
});

test('empty query is a local error without network call', async () => {
  let called = false;
  await assert.rejects(
    () => searchCompanies('', { fetchImpl: async () => { called = true; return { ok: true, json: async () => ({}) }; } }),
    /поисковый запрос|Введите/i,
  );
  assert.equal(called, false);
});

test('abc in name mode is rejected locally', async () => {
  let called = false;
  await assert.rejects(
    () => searchCompanies('abc', { fetchImpl: async () => { called = true; return { ok: true, json: async () => ({}) }; } }),
    /4 символа/,
  );
  assert.equal(called, false);
});

test('pagination sends page and preserves filters', async () => {
  const urls = [];
  const data = await searchCompanies('ростелеком', {
    fetchImpl: makeFetch(urls),
    page: 2,
    region: '77',
    active: false,
  });
  assert.match(urls[0], /page=2/);
  assert.match(urls[0], /region=77/);
  assert.match(urls[0], /active=false/);
  assert.equal(data.totalPages, 3);
  assert.equal(data.page, 1); // server reports current page
});

test('active=false is sent as false not dropped', async () => {
  const urls = [];
  await searchCompanies('ростелеком', { fetchImpl: makeFetch(urls), active: false });
  assert.match(urls[0], /active=false/);
  assert.ok(!urls[0].includes('active=true'));
});

test('date 2020-12-31 is search by date not phone', async () => {
  const urls = [];
  await searchCompanies('2020-12-31', { fetchImpl: makeFetch(urls) });
  assert.match(urls[0], /by=reg-date/);
});
