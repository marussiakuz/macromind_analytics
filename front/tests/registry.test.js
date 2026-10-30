import assert from 'node:assert/strict';
import test from 'node:test';
import {
  REGISTRY_SECTIONS,
  fetchCompanyRegistry,
  fetchContractsRegistry,
} from '../src/api/companyRegistry.js';
import {
  renderRegistrySection,
  renderRegistryLoadingHTML,
  renderRegistryErrorHTML,
  COLLAPSED_COUNT,
} from '../src/render/registry.js';

function makeItems(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: `id-${i}`,
    title: `Запись ${i + 1}`,
    date: `2026-0${(i % 9) + 1}-10`,
    status: 'Действует',
    amount: 1000 + i,
    url: i === 0 ? 'https://example.com' : null,
    fields: { Суд: `Суд ${i + 1}`, Нарушения: i % 2 ? 'да' : 'нет' },
  }));
}

test('six registry sections defined in flow order', () => {
  assert.equal(REGISTRY_SECTIONS.length, 6);
  assert.deepEqual(
    REGISTRY_SECTIONS.map(s => s.method),
    ['legal-cases', 'enforcements', 'contracts', 'fedresurs', 'bankruptcy-messages', 'inspections'],
  );
});

test('section shows 5 rows and expand button', () => {
  const html = renderRegistrySection({
    id: 'registry-card-legalCases',
    title: 'Арбитражные дела',
    subtitle: 'Иски',
    items: makeItems(12),
    expandKey: 'legalCases',
    expanded: false,
  });
  assert.match(html, /Запись 1/);
  assert.match(html, /Запись 5/);
  assert.ok(!html.includes('Запись 7'));
  assert.match(html, /Развернуть ещё 7/);
  assert.match(html, /registry-card-legalCases/);
});

test('expanded section shows all and collapse button', () => {
  const html = renderRegistrySection({
    id: 'x',
    title: 't',
    items: makeItems(8),
    expandKey: 'legalCases',
    expanded: true,
  });
  assert.match(html, /Запись 8/);
  assert.match(html, /Свернуть/);
});

test('short list has no toggle', () => {
  const html = renderRegistrySection({
    id: 'x',
    title: 't',
    items: makeItems(3),
    expandKey: 'k',
    expanded: false,
  });
  assert.ok(!html.includes('registry-toggle'));
});

test('fetchCompanyRegistry maps ok and empty', async () => {
  let url = '';
  const ok = await fetchCompanyRegistry('legal-cases', '7707049388', {
    fetchImpl: async (u) => {
      url = u;
      return {
        ok: true,
        json: async () => ({
          registry: {
            inn: '7707049388',
            method: 'legal-cases',
            items: makeItems(2),
          },
        }),
      };
    },
  });
  assert.match(url, /registry\/legal-cases/);
  assert.equal(ok.status, 'ok');

  const empty = await fetchCompanyRegistry('enforcements', '7707049388', {
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ registry: { inn: '7707049388', items: [] } }),
    }),
  });
  assert.equal(empty.status, 'empty');
});

test('fetchContractsRegistry merges 44 and 223', async () => {
  const res = await fetchContractsRegistry('7707049388', {
    fetchImpl: async (url) => ({
      ok: true,
      json: async () => ({
        registry: {
          inn: '7707049388',
          method: 'contracts',
          items: url.includes('law=44')
            ? [{ id: '44-1', title: '44-ФЗ контракт' }]
            : [{ id: '223-1', title: '223-ФЗ договор' }],
        },
      }),
    }),
  });
  assert.equal(res.status, 'ok');
  assert.equal(res.registry.items.length, 2);
});

test('loading and error placeholders', () => {
  assert.match(renderRegistryLoadingHTML('id', 'Заголовок'), /Загружаем/);
  assert.match(renderRegistryLoadingHTML('id', 'Заголовок'), /animate-spin/);
  const err = renderRegistryErrorHTML('id', 't', 'boom <script>');
  assert.ok(!err.includes('<script>'));
});

test('COLLAPSED_COUNT is 5', () => {
  assert.equal(COLLAPSED_COUNT, 5);
});
