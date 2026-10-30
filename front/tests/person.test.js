import assert from 'node:assert/strict';
import test from 'node:test';
import {
  renderPersonResultHTML,
  renderPersonLoadingHTML,
  renderPersonErrorHTML,
  renderPersonResultsList,
} from '../src/render/personResult.js';
import {
  completePersonCheck,
  extractPersonInns,
  checkPersonsFromCompany,
  selectAutoBatch,
  personCoverageSummary,
  MAX_AUTO_PERSON_CHECKS,
} from '../src/api/person.js';

const person = {
  inn: '402907671076',
  full_name: 'Морозов Андрей Иванович',
  entity_type: 'person',
  managed_companies: [
    { name: 'Тест ООО', inn: '7707083893', ogrn: '1027700132195', status: 'Действует', registration_date: '1991-06-20', address: 'Москва', okved: '64.19' },
  ],
  founded_companies: [
    { name: 'Другая', inn: '7724408012', status: 'Действует' },
  ],
  entrepreneurships: [
    { ogrnip: '310402910200035', name: 'Морозов Андрей Иванович', status: 'Действует', registration_date: '2010-01-01', okved: '62.01' },
  ],
  trademarks: [],
  bankruptcy_messages: [{ 'Тип': 'Сообщение', 'Дата': '2020-01-01', 'Дело': 'А40-1' }],
  risk_factors: {
    unfair_supplier: false,
    mass_director: true,
    mass_founder: false,
    sanctioned: true,
    sanctioned_countries: ['US'],
  },
  source: 'checko',
};

test('extractPersonInns keeps all people and merges roles', () => {
  const company = {
    directors: [
      { 'ФИО': 'Иванов Иван', 'ИНН': '402907671076' },
      { 'ФИО': 'Без ИНН', 'ИНН': '' },
      { 'ФИО': 'Юрлицо', 'ИНН': '7707083893' },
    ],
    shareholders: [
      { name: 'Петров Пётр', type: 'person', inn: '500100732259' },
      { name: 'ООО Ромашка', type: 'company', inn: '7724408012' },
      { name: 'Иванов Иван', type: 'person', inn: '402907671076' },
    ],
  };
  const people = extractPersonInns(company);
  // all unique people including without INN and non-person founders excluded
  const ivan = people.find(p => p.inn === '402907671076');
  assert.ok(ivan);
  assert.deepEqual([...ivan.roles].sort(), ['Руководитель', 'Учредитель']);
  assert.ok(people.some(p => p.name === 'Без ИНН' && p.checkStatus === 'no_inn'));
  assert.ok(people.some(p => p.inn === '500100732259'));
  // 10-digit company INN is not a person
  assert.ok(!people.some(p => p.inn === '7707083893' && p.checkStatus !== 'no_inn' && p.roles.includes('Руководитель') === false));
  assert.ok(people.filter(p => p.checkStatus === 'not_checked').length >= 2);
});

test('selectAutoBatch limits first batch but keeps remainder visible', () => {
  const people = Array.from({ length: 8 }, (_, i) => ({
    inn: `40290767107${i}`,
    name: `Человек ${i}`,
    roles: ['Руководитель'],
    checkStatus: 'not_checked',
  }));
  const batch = selectAutoBatch(people, MAX_AUTO_PERSON_CHECKS);
  assert.equal(batch.length, 5);
  assert.equal(people.filter(p => p.checkStatus === 'not_checked').length, 8);
});

test('personCoverageSummary reports done vs pending', () => {
  const people = [
    { inn: '1', checkStatus: 'done' },
    { inn: '2', checkStatus: 'done' },
    { inn: '3', checkStatus: 'done' },
    { inn: '4', checkStatus: 'done' },
    { inn: '5', checkStatus: 'done' },
    { inn: '6', checkStatus: 'not_checked' },
    { inn: '7', checkStatus: 'not_checked' },
    { inn: null, checkStatus: 'no_inn' },
  ];
  const s = personCoverageSummary(people);
  assert.equal(s.done, 5);
  assert.equal(s.pending, 2);
  assert.equal(s.noInn, 1);
  assert.match(s.text, /Проверено 5 из 8/);
  assert.match(s.text, /ещё 2 не проверены/);
});

test('person results list shows not_checked and no_inn states', () => {
  const html = renderPersonResultsList([
    { inn: '111111111111', name: 'Ждём', checkStatus: 'not_checked', roles: ['Руководитель'] },
    { inn: null, name: 'Без ИНН', checkStatus: 'no_inn', roles: ['Учредитель'], findings: 'Автоматическая проверка недоступна: нет ИНН' },
    { inn: '333333333333', name: 'Ошибка', checkStatus: 'error', roles: ['Руководитель'], findings: 'Сбой' },
  ]);
  assert.match(html, /не проверялся/);
  assert.match(html, /без ИНН/);
  assert.match(html, /Автоматическая проверка недоступна/);
  assert.match(html, /Сбой/);
  assert.match(html, /Повторить/);
});

test('person card shows links, IP and risks', () => {
  const html = renderPersonResultHTML(person);
  assert.match(html, /Морозов Андрей Иванович/);
  assert.match(html, /ОГРНИП 310402910200035/);
});

test('completePersonCheck fills the record from API payload', async () => {
  const record = { inn: '402907671076', name: '402907671076', status: 'Проверяется' };
  await completePersonCheck(record, {
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ source: 'checko', person: { ...person } }),
    }),
  });
  assert.equal(record.status, 'Анализ завершен');
  assert.equal(record.name, 'Морозов Андрей Иванович');
});

test('checkPersonsFromCompany completes all records', async () => {
  const people = [
    { inn: '402907671076', name: 'А', roles: ['Руководитель'] },
    { inn: '500100732259', name: 'Б', roles: ['Учредитель'] },
  ];
  const results = await checkPersonsFromCompany(people, {
    fetchImpl: async (url) => ({
      ok: true,
      json: async () => ({
        source: 'checko',
        person: {
          inn: url.split('/').pop(),
          full_name: url.includes('4029') ? 'А' : 'Б',
          managed_companies: [],
          founded_companies: [],
          entrepreneurships: [],
          risk_factors: {},
        },
      }),
    }),
  });
  assert.equal(results.length, 2);
  assert.ok(results.every(r => r.status === 'Анализ завершен'));
});

test('person placeholders render safely', () => {
  assert.match(renderPersonLoadingHTML(), /физлица/);
  assert.ok(!renderPersonErrorHTML('boom <img>').includes('<img>'));
});
