import assert from 'node:assert/strict';
import test from 'node:test';
import { completeCompanyCheck } from '../src/api/counterparty.js';

const pending = () => ({ inn: '5040201979', name: '5040201979', status: 'Проверяется' });

test('company check calls the API and completes the original history record', async () => {
  const record = pending();
  const result = await completeCompanyCheck(record, { fetchImpl: async (url) => {
    assert.equal(url, 'http://localhost:8000/api/v1/counterparties/5040201979');
    return { ok: true, json: async () => ({ source: 'checko', company: {
      inn: record.inn, name: 'Реальная компания', status: 'Действует',
      director: 'Иван Иванов', risk_factors: { sanctioned: false },
    } }) };
  } });
  assert.equal(result, record);
  assert.equal(record.status, 'Анализ завершен');
  assert.equal(record.name, 'Реальная компания');
  assert.match(record.findings, /Иван Иванов/);
  assert.equal(record.riskLevel, null);
});

test('provider failure replaces the pending state with a useful error', async () => {
  const record = pending();
  await completeCompanyCheck(record, { fetchImpl: async () => ({
    ok: false, status: 502, json: async () => ({ detail: 'Checko не ответил вовремя' }),
  }) });
  assert.equal(record.status, 'Ошибка проверки');
  assert.equal(record.findings, 'Checko не ответил вовремя');
});

test('network failure cannot leave a check pending', async () => {
  const record = pending();
  await completeCompanyCheck(record, { fetchImpl: async () => { throw new TypeError('Failed to fetch'); } });
  assert.equal(record.status, 'Ошибка проверки');
  assert.match(record.findings, /связаться с сервером/);
});

test('timeout cancels the request and finishes the pending record', async () => {
  const record = pending();
  await completeCompanyCheck(record, { timeoutMs: 5, fetchImpl: (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('aborted')));
  }) });
  assert.equal(record.status, 'Ошибка проверки');
  assert.match(record.findings, /не ответил вовремя/);
});

test('wrong INN and malformed data cannot become successful checks', async () => {
  for (const company of [null, { inn: '7707083893', name: 'Другой контрагент' }]) {
    const record = pending();
    await completeCompanyCheck(record, { fetchImpl: async () => ({ ok: true, json: async () => ({ company }) }) });
    assert.equal(record.status, 'Ошибка проверки');
  }
});
