import assert from 'node:assert/strict';
import test from 'node:test';
import {
  renderCheckResultHTML,
  renderCheckLoadingHTML,
  renderCheckErrorHTML,
} from '../src/render/checkResult.js';

const company = {
  inn: '7707083893',
  ogrn: '1027700132195',
  name: 'Тест',
  full_name: 'Полное название',
  entity_type: 'company',
  legal_form: 'ПАО',
  registration_date: '1991-06-20',
  status: 'Действует',
  address: 'Москва',
  okved_main: '63.11',
  okved_description: 'Деятельность в области ИТ',
  charter_capital: 1000000,
  director: 'Иван Иванов',
  directors: [{ 'ФИО': 'Иван Иванов', 'ИНН': '123', 'НаимДолжн': 'Генеральный директор' }],
  shareholders: [{ name: 'Пётр Петров', type: 'person', inn: '456', share_percent: 25 }],
  risk_factors: { sanctioned: true, mass_director: false },
  contacts: { 'Тел': ['+7 495 000-00-00'], 'Емэйл': ['a@b.ru'], 'ВебСайт': 'example.com' },
  source: 'checko',
};

test('result card shows requisites, people, risks and contacts', () => {
  const html = renderCheckResultHTML(company, {
    requestedAt: '2026-10-19',
    source: 'checko',
  });
  assert.match(html, /7707083893/);
  assert.match(html, /1027700132195/);
  assert.match(html, /Иван Иванов/);
  assert.match(html, /Пётр Петров/);
  assert.match(html, /Санкции в отношении компании/);
  assert.match(html, /example\.com/);
  assert.match(html, /Действует/);
});

test('result card escapes HTML from API fields', () => {
  const html = renderCheckResultHTML({
    ...company,
    name: '<script>alert(1)</script>',
    full_name: '<img src=x onerror=alert(1)>',
  });
  assert.ok(!html.includes('<script>alert(1)</script>'));
  assert.ok(!html.includes('<img src=x'));
  assert.match(html, /&lt;script&gt;/);
});

test('no-risk company gets a calm risk block', () => {
  const html = renderCheckResultHTML({
    ...company,
    risk_factors: { sanctioned: false, mass_director: false },
  });
  assert.match(html, /нет отмеченных факторов риска/);
  assert.ok(!html.includes('Санкции в отношении компании'));
});

test('loading and error placeholders render safely', () => {
  assert.match(renderCheckLoadingHTML(), /Загружаем данные проверки/);
  const err = renderCheckErrorHTML('boom <script>');
  assert.ok(!err.includes('<script>'));
  assert.match(err, /boom/);
});
