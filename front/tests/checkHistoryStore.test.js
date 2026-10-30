import assert from 'node:assert/strict';
import test from 'node:test';
import {
  loadCheckHistoryState,
  saveCheckHistoryState,
  persistFromAppState,
  hydrateAppState,
} from '../src/checkHistoryStore.js';

function fakeStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  };
}

function withStorage(fn) {
  const prev = globalThis.localStorage;
  Object.defineProperty(globalThis, 'localStorage', {
    value: fakeStorage(),
    configurable: true,
    writable: true,
  });
  try {
    return fn();
  } finally {
    if (prev === undefined) {
      delete globalThis.localStorage;
    } else {
      Object.defineProperty(globalThis, 'localStorage', {
        value: prev,
        configurable: true,
        writable: true,
      });
    }
  }
}

test('history survives save/load cycle', () => {
  withStorage(() => {
    const ok = saveCheckHistoryState({
      checkHistory: [
        { id: 'check-1', inn: '5040133380', name: 'ГидроЭл', status: 'Анализ завершен', company: { name: 'ГидроЭл' } },
      ],
      personCheckHistory: [],
      selectedCheckId: 'check-1',
    });
    assert.equal(ok, true);
    const loaded = loadCheckHistoryState();
    assert.equal(loaded.checkHistory.length, 1);
    assert.equal(loaded.checkHistory[0].inn, '5040133380');
    assert.equal(loaded.selectedCheckId, 'check-1');
  });
});

test('hydrate restores selected record and marks interrupted checks', () => {
  withStorage(() => {
    saveCheckHistoryState({
      checkHistory: [
        { id: 'a', inn: '1', status: 'Анализ завершен', company: { name: 'X' }, finances: { years: [] } },
        { id: 'b', inn: '2', status: 'Проверяется' },
      ],
      selectedCheckId: 'a',
    });
    const state = { checkHistory: [], personCheckHistory: [], selectedCheckResult: null };
    hydrateAppState(state);
    assert.equal(state.checkHistory.length, 2);
    assert.equal(state.selectedCheckResult?.id, 'a');
    const interrupted = state.checkHistory.find((r) => r.id === 'b');
    assert.equal(interrupted.status, 'Ошибка проверки');
  });
});

test('persistFromAppState reads checkHistory from state', () => {
  withStorage(() => {
    persistFromAppState({
      checkHistory: [{ id: 'c1', inn: '5040133380', status: 'Анализ завершен' }],
      personCheckHistory: [{ id: 'p1', inn: '123', status: 'Анализ завершен', person: {} }],
      selectedCheckResult: { id: 'c1' },
      selectedPersonResult: { id: 'p1' },
    });
    const loaded = loadCheckHistoryState();
    assert.equal(loaded.checkHistory[0].id, 'c1');
    assert.equal(loaded.personCheckHistory[0].id, 'p1');
    assert.equal(loaded.selectedCheckId, 'c1');
    assert.equal(loaded.selectedPersonId, 'p1');
  });
});

test('oversized payloads drop oldest checks', () => {
  withStorage(() => {
    const big = { blob: 'x'.repeat(600_000) };
    const checks = Array.from({ length: 10 }, (_, i) => ({
      id: `id-${i}`, inn: String(1000000000 + i), status: 'Анализ завершен', ...big,
    }));
    const ok = saveCheckHistoryState({ checkHistory: checks, personCheckHistory: [] });
    assert.equal(ok, true);
    const loaded = loadCheckHistoryState();
    assert.ok(loaded.checkHistory.length >= 1);
    assert.ok(loaded.checkHistory.length < 10, `expected shrink, got ${loaded.checkHistory.length}`);
  });
});
