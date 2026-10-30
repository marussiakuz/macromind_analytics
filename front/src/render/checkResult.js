import { riskLabels } from '../api/counterparty.js';
import { formatDate } from '../utils/helpers.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function row(label, value) {
  if (value === null || value === undefined || value === '') return '';
  return `
    <div class="flex flex-col gap-1">
      <span class="text-xs text-text-secondary">${escapeHtml(label)}</span>
      <span class="text-sm text-text-main">${escapeHtml(value)}</span>
    </div>
  `;
}

function section(title, body) {
  if (!body) return '';
  return `
    <div>
      <h3 class="text-sm font-semibold text-text-main mb-3">${escapeHtml(title)}</h3>
      ${body}
    </div>
  `;
}

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return `${num.toLocaleString('ru-RU')} ₽`;
}

export function renderCheckLoadingHTML() {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-8 slide-up">
      <div class="flex items-center gap-4">
        <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
        <div>
          <h2 class="text-lg font-semibold text-text-main">Загружаем данные проверки</h2>
          <p class="text-sm text-text-secondary mt-1">Собираем сведения о компании, финансах, историях и рисках…</p>
        </div>
      </div>
    </div>
  `;
}

export function renderCheckErrorHTML(message) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-8 slide-up border border-red-800/40">
      <div class="flex items-start gap-3">
        <i data-lucide="alert-circle" class="w-6 h-6 text-red-400 shrink-0 mt-0.5"></i>
        <div>
          <h2 class="text-lg font-semibold text-text-main mb-1">Ошибка проверки</h2>
          <p class="text-sm text-text-secondary">${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

/**
 * Карточка результата проверки по данным Checko (company.md / ЕГРЮЛ).
 * @param {object} company — нормализованный ответ API
 * @param {object|null} record — запись истории (опционально)
 */
export function renderCheckResultHTML(company, record = null) {
  if (!company) return '';

  const risks = Object.entries(company.risk_factors || {})
    .filter(([, value]) => value === true)
    .map(([key]) => riskLabels[key] || key);

  const directors = (company.directors || []).map(d => ({
    name: d['ФИО'] || d.ФИО || '',
    inn: d['ИНН'] || d.ИНН || '',
    position: d['НаимДолжн'] || d.НаимДолжн || '',
  })).filter(d => d.name);

  const shareholders = company.shareholders || [];
  const contacts = company.contacts || {};
  const phones = contacts['Тел'] || contacts.Тел || [];
  const emails = contacts['Емэйл'] || contacts.Емэйл || [];
  const website = contacts['ВебСайт'] || contacts.ВебСайт || '';

  const statusOk = (company.status || '').toLowerCase().includes('действ')
    || (company.status || '').toLowerCase().includes('зарегистрир');

  const requisites = `
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
      ${row('ИНН', company.inn)}
      ${row('ОГРН', company.ogrn)}
      ${row('Тип', company.entity_type === 'entrepreneur' ? 'ИП' : 'Организация')}
      ${row('Организационно-правовая форма', company.legal_form)}
      ${row('Дата регистрации', company.registration_date ? formatDate(company.registration_date) : null)}
      ${row('Уставный капитал', formatMoney(company.charter_capital))}
    </div>
  `;

  const activity = `
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      ${row('Адрес', company.address)}
      ${row('ОКВЭД', company.okved_main ? `${company.okved_main}${company.okved_description ? ` — ${company.okved_description}` : ''}` : null)}
    </div>
  `;

  const people = (directors.length || shareholders.length) ? `
    <div class="space-y-4">
      ${directors.length ? `
        <div>
          <h4 class="text-xs text-text-secondary mb-2">Руководители</h4>
          <div class="space-y-2">
            ${directors.map(d => `
              <div class="flex flex-wrap items-center gap-2 text-sm">
                <span class="text-text-main font-medium">${escapeHtml(d.name)}</span>
                ${d.position ? `<span class="text-text-secondary">· ${escapeHtml(d.position)}</span>` : ''}
                ${d.inn ? `<span class="text-text-secondary text-xs">ИНН ${escapeHtml(d.inn)}</span>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
      ${shareholders.length ? `
        <div>
          <h4 class="text-xs text-text-secondary mb-2">Учредители</h4>
          <div class="space-y-2">
            ${shareholders.map(s => `
              <div class="flex flex-wrap items-center gap-2 text-sm">
                <span class="text-text-main font-medium">${escapeHtml(s.name)}</span>
                <span class="text-text-secondary text-xs">${s.type === 'person' ? 'ФЛ' : 'ЮЛ'}</span>
                ${s.inn ? `<span class="text-text-secondary text-xs">ИНН ${escapeHtml(s.inn)}</span>` : ''}
                ${s.share_percent !== null && s.share_percent !== undefined
                  ? `<span class="text-text-secondary text-xs">доля ${escapeHtml(s.share_percent)}%</span>`
                  : ''}
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
    </div>
  ` : '';

  const riskBody = risks.length
    ? `
      <div class="flex flex-wrap gap-2">
        ${risks.map(r => `
          <span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-red-900/[.30] text-red-400 border border-red-800/40">
            ${escapeHtml(r)}
          </span>
        `).join('')}
      </div>
    `
    : `
      <p class="text-sm text-text-secondary">
        В полученных сведениях нет отмеченных факторов риска.
        Полная оценка надёжности не запрашивалась.
      </p>
    `;

  const contactParts = [
    phones.length ? `<div><span class="text-xs text-text-secondary">Телефоны</span><div class="text-sm text-text-main">${phones.map(p => escapeHtml(p)).join('<br>')}</div></div>` : '',
    emails.length ? `<div><span class="text-xs text-text-secondary">Email</span><div class="text-sm text-text-main">${emails.map(e => escapeHtml(e)).join('<br>')}</div></div>` : '',
    website ? `<div><span class="text-xs text-text-secondary">Сайт</span><div class="text-sm text-text-main">${escapeHtml(website)}</div></div>` : '',
  ].filter(Boolean).join('');

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" id="check-result-card">
      <div class="p-6 border-b border-card-border flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="flex items-center gap-3 flex-wrap">
            <h2 class="text-xl font-semibold text-text-main">${escapeHtml(company.full_name || company.name)}</h2>
            <span class="px-3 py-1 rounded-full text-xs font-medium ${
              statusOk
                ? 'bg-green-900/[.30] text-green-400'
                : 'bg-amber-900/[.30] text-amber-400'
            }">
              ${escapeHtml(company.status || 'Статус неизвестен')}
            </span>
          </div>
          ${company.name && company.full_name && company.name !== company.full_name
            ? `<p class="text-sm text-text-secondary mt-1">${escapeHtml(company.name)}</p>`
            : ''}
          ${record?.requestedAt
            ? `<p class="text-xs text-text-secondary mt-2">Проверка от ${escapeHtml(formatDate(record.requestedAt))} · источник: ЕГРЮЛ</p>`
            : ''}
        </div>
        <div class="flex items-center gap-2">
          ${risks.length
            ? `<span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-red-900/[.30] text-red-400 border border-red-800/40">Риск: требует внимания</span>`
            : `<span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-green-900/[.30] text-green-400 border border-green-800/40">Факторы риска не отмечены</span>`}
        </div>
      </div>

      <div class="p-6 space-y-6 divide-y divide-card-border">
        ${section('Реквизиты', requisites)}
        ${section('Деятельность', activity)}
        ${section('Люди', people)}
        ${section('Факторы риска', riskBody)}
        ${contactParts ? section('Контакты', `<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">${contactParts}</div>`) : ''}
      </div>
    </div>
  `;
}
