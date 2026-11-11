import { renderPitchDeckTab } from './pitchDeck.js';
import { mockProjects } from '../data/mockData.js';
import { formatDate, getStatusColor } from '../utils/helpers.js';
import { renderHeader } from './header.js';
import { renderNotificationsHTML } from '../notifications.js';
import { state } from '../state.js';
import { renderPortfolioDashboard } from './portfolioDashboard.js';
import { renderCompanies } from './companies.js';
import { renderObligations } from './obligations.js';
import { renderAiAssistant } from './aiAssistant.js';
import { renderCompetencyTab } from './competency.js';
import { renderWeakSignalsTab } from './weakSignals.js';
import { personCoverageSummary } from '../api/person.js';
import { renderCheckResultHTML, renderCheckLoadingHTML, renderCheckErrorHTML } from './checkResult.js';
import {
  renderPersonResultHTML,
  renderPersonResultsList,
  renderPersonLoadingHTML,
  renderPersonErrorHTML,
} from './personResult.js';
import {
  renderFinancesHTML,
  renderFinancesErrorHTML,
} from './finances.js';
import {
  renderTimelineHTML,
  renderTimelineErrorHTML,
} from './timeline.js';
import {
  renderRegistrySection,
  renderRegistryErrorHTML,
} from './registry.js';
import { REGISTRY_SECTIONS } from '../api/companyRegistry.js';
import { renderMarketSummaryHTML } from './market.js';
import { marketState } from '../market/state.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

/** Кружок загрузки в шапке модуля (без дёрганья). */
function loadingSpinner(size = 'w-4 h-4') {
  return `<div class="animate-spin ${size} border-2 border-primary border-t-transparent rounded-full shrink-0" aria-label="Загрузка"></div>`;
}

function moduleHeader(title, { subtitle = '', loading = false, extra = '' } = {}) {
  return `
    <div class="flex items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-text-main flex items-center gap-2">
          ${escapeHtml(title)}
          ${loading ? loadingSpinner() : ''}
        </h2>
        ${subtitle ? `<p class="text-sm text-text-secondary mt-1">${escapeHtml(subtitle)}</p>` : ''}
      </div>
      ${extra}
    </div>
  `;
}

const SECTIONS = [
  { id: 'funnel',       icon: 'git-merge',   label: 'Воронка' },
  { id: 'portfolio',    icon: 'briefcase',   label: 'Портфель' },
  { id: 'weak-signals', icon: 'radio',       label: 'Поиск слабых сигналов' },
  { id: 'archive',      icon: 'archive',     label: 'Архив' },
];

const FUNNEL_TABS = [
  { id: 'projects',       icon: 'layers',       label: 'Воронка сделок'     },
  { id: 'check-company',  icon: 'search',       label: 'Поиск'              },
  { id: 'pitch-decks',    icon: 'file-text',    label: 'Питч-деки'          },
];

const PORTFOLIO_TABS = [
  { id: 'portfolio',   icon: 'layout-dashboard', label: 'Обзор'          },
  { id: 'companies',   icon: 'building-2',        label: 'Компании'       },
  { id: 'obligations', icon: 'calendar-clock',    label: 'Обязательства'  },
  { id: 'assistant',   icon: 'bot',               label: 'AI-ассистент'   },
];

function renderFundSidebar() {
  const subTabs = state.fundPhase === 'funnel' ? FUNNEL_TABS
               : state.fundPhase === 'portfolio' ? PORTFOLIO_TABS
               : [];

  return `
    <aside class="w-64 bg-surface border-r border-card-border flex flex-col h-full shrink-0">
      <!-- Верхний уровень: 3 секции -->
      <nav class="px-4 pt-4 space-y-0.5">
        ${SECTIONS.map(s => {
          const active = state.fundPhase === s.id;
          return `
            <button
              type="button"
              class="fund-phase-btn w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl transition-all font-semibold ${
                active
                  ? 'bg-primary text-white shadow-soft'
                  : 'text-text-secondary hover:bg-[#222222] hover:text-text-main'
              }"
              data-phase="${s.id}"
            >
              <i data-lucide="${s.icon}" class="w-4 h-4 shrink-0"></i>
              <span class="text-sm">${s.label}</span>
            </button>
          `;
        }).join('')}
      </nav>

      ${subTabs.length > 0 ? `
        <!-- Разделитель -->
        <div class="mx-4 my-3 border-t border-card-border"></div>

        <!-- Вторичная навигация активной секции -->
        <nav class="px-4 space-y-0.5">
          ${subTabs.map(tab => {
            const isActive = state.fundPhase === 'funnel'
              ? state.currentFundTab === tab.id
              : state.currentPostTab === tab.id;
            const btnClass = state.fundPhase === 'funnel' ? 'fund-nav-btn' : 'post-nav-btn';
            const dataAttr = state.fundPhase === 'funnel'
              ? `data-tab="${tab.id}"`
              : `data-post-tab="${tab.id}"`;
            return `
              <button
                type="button"
                class="${btnClass} w-full text-left flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all font-medium ${
                  isActive
                    ? 'bg-primary/[.18] text-primary'
                    : 'text-text-secondary hover:bg-[#222222] hover:text-text-main'
                }"
                ${dataAttr}
              >
                <i data-lucide="${tab.icon}" class="w-4 h-4 shrink-0"></i>
                <span class="text-sm">${tab.label}</span>
              </button>
            `;
          }).join('')}
        </nav>
      ` : ''}
    </aside>
  `;
}

function renderProjectsTab() {
  return `
    <div class="flex-1 flex flex-col">
      <div class="mb-8 slide-up">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-2xl font-semibold text-text-main mb-2">Воронка сделок</h1>
            <p class="text-text-secondary">Управление и анализ проектов на стадии DD</p>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-3">
            <button
              type="button"
              id="invite-link-btn"
              class="inline-flex items-center gap-2 px-4 py-2 bg-card border border-[#484848] rounded-xl text-sm font-medium text-text-main hover:bg-[#222222] transition-all shadow-soft"
            >
              <i data-lucide="link-2" class="w-4 h-4 shrink-0 text-text-secondary"></i>
              Пригласительная ссылка
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-2 px-4 py-2 bg-card border border-[#484848] rounded-xl text-sm font-medium text-text-main hover:bg-[#222222] transition-all shadow-soft"
            >
              <i data-lucide="filter" class="w-4 h-4 shrink-0 text-text-secondary"></i>
              Фильтры
            </button>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-8 slide-up" style="animation-delay: 0.1s">
        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex items-center gap-3 mb-3">
            <div class="w-10 h-10 rounded-full bg-primary/[.18] flex items-center justify-center">
              <i data-lucide="inbox" class="w-5 h-5 text-primary"></i>
            </div>
            <span class="text-text-secondary text-sm">Всего проектов</span>
          </div>
          <div class="text-3xl font-bold text-text-main">${mockProjects.length}</div>
        </div>
        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex items-center gap-3 mb-3">
            <div class="w-10 h-10 rounded-full bg-amber-900/[.30] flex items-center justify-center">
              <i data-lucide="search" class="w-5 h-5 text-amber-400"></i>
            </div>
            <span class="text-text-secondary text-sm">На анализе</span>
          </div>
          <div class="text-3xl font-bold text-text-main">${mockProjects.filter(p => p.status === 'На анализе').length}</div>
        </div>
        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex items-center gap-3 mb-3">
            <div class="w-10 h-10 rounded-full bg-purple-900/[.30] flex items-center justify-center">
              <i data-lucide="users" class="w-5 h-5 text-purple-400"></i>
            </div>
            <span class="text-text-secondary text-sm">Решение ИК</span>
          </div>
          <div class="text-3xl font-bold text-text-main">${mockProjects.filter(p => p.status === 'Решение ИК').length}</div>
        </div>
        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex items-center gap-3 mb-3">
            <div class="w-10 h-10 rounded-full bg-green-900/[.30] flex items-center justify-center">
              <i data-lucide="check" class="w-5 h-5 text-green-400"></i>
            </div>
            <span class="text-text-secondary text-sm">Завершено</span>
          </div>
          <div class="text-3xl font-bold text-text-main">${mockProjects.filter(p => p.status === 'Результат').length}</div>
        </div>
      </div>

      <div class="bg-card rounded-2xl shadow-soft slide-up flex-1" style="animation-delay: 0.2s">
        <div class="p-6 border-b border-card-border">
          <h2 class="text-xl font-semibold text-text-main">Все проекты</h2>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-surface">
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Проект</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">ИНН</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Статус</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Документы</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Аналитик</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Дата подачи</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Действия</th>
              </tr>
            </thead>
            <tbody>
              ${mockProjects.map((project, index) => `
                <tr class="border-t border-card-border hover:bg-[#222222] transition-colors cursor-pointer project-row" data-project-id="${project.id}" style="animation-delay: ${index * 0.05}s">
                  <td class="px-6 py-4">
                    <div class="font-medium text-text-main">${project.name}</div>
                    <div class="text-sm text-text-secondary">${project.industry} · ${project.stage_funding}</div>
                  </td>
                  <td class="px-6 py-4 text-text-secondary">${project.inn}</td>
                  <td class="px-6 py-4">
                    <span class="px-3 py-1 ${getStatusColor(project.status)} rounded-full text-sm font-medium">${project.status}</span>
                  </td>
                  <td class="px-6 py-4">
                    <div class="flex items-center gap-2">
                      <div class="w-24 h-2 bg-surface rounded-full overflow-hidden">
                        <div class="h-full bg-primary rounded-full" style="width: ${project.progress}%"></div>
                      </div>
                      <span class="text-sm text-text-secondary">${project.documentsUploaded}/${project.documentsRequired}</span>
                    </div>
                  </td>
                  <td class="px-6 py-4 text-text-secondary">${project.assignedAnalyst}</td>
                  <td class="px-6 py-4 text-text-secondary">${formatDate(project.submittedAt)}</td>
                  <td class="px-6 py-4">
                    <button type="button" class="view-project-btn px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm rounded-lg font-medium transition-all">
                      Просмотр
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderCompanyHistoryList() {
  const history = state.checkHistory || [];
  if (history.length === 0) {
    return '<div class="p-6 text-center text-text-secondary">История пуста. Начните с первой проверки.</div>';
  }
  return history.map(record => {
    const active = state.selectedCheckResult?.id === record.id;
    const personCount = record.personResults?.length || 0;
    return `
      <div
        class="p-6 hover:bg-[#222222] transition-colors ${record.company ? 'cursor-pointer check-history-item' : ''} ${active ? 'bg-[#222222]' : ''}"
        ${record.company ? `data-check-id="${escapeHtml(record.id)}"` : ''}
      >
        <div class="flex items-start justify-between mb-3">
          <div class="flex-1">
            <h3 class="font-semibold text-text-main">${escapeHtml(record.name)}</h3>
            <p class="text-sm text-text-secondary mt-1">
              ИНН: ${escapeHtml(record.inn)}${record.url ? ` · ${escapeHtml(record.url)}` : ''}
            </p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <span class="px-3 py-1 rounded-full text-xs font-medium ${
              record.status === 'Анализ завершен' || record.status === 'Завершено'
                ? 'bg-green-900/[.30] text-green-400'
                : record.status === 'Ошибка проверки'
                  ? 'bg-red-900/[.30] text-red-400'
                : record.status === 'Проверяется' || record.status === 'На процессе'
                  ? 'bg-amber-900/[.30] text-amber-400'
                  : 'bg-primary/[.18] text-primary'
            }">
              ${escapeHtml(record.status)}
            </span>
            ${personCount ? `
              <span class="px-2 py-1 rounded-lg text-xs bg-primary/[.18] text-primary">
                физлиц: ${personCount}
              </span>
            ` : ''}
          </div>
        </div>
        <div class="flex items-center gap-4 text-sm mb-3">
          <span class="text-text-secondary">Запрошено: ${formatDate(record.requestedAt)}</span>
          ${record.riskLevel ? `
            <span class="px-2 py-1 rounded-lg text-xs ${
              record.riskLevel === 'Низкий'
                ? 'bg-green-900/[.30] text-green-400'
                : record.riskLevel === 'Средний'
                  ? 'bg-amber-900/[.30] text-amber-400'
                  : 'bg-red-900/[.30] text-red-400'
            }">Риск: ${escapeHtml(record.riskLevel)}</span>
          ` : ''}
        </div>
        ${record.findings ? `<p class="text-sm text-text-secondary whitespace-pre-line">${escapeHtml(record.findings)}</p>` : ''}
        ${record.source ? `<p class="text-xs text-text-secondary mt-3">Источник: ${escapeHtml(record.source)}</p>` : ''}
      </div>
    `;
  }).join('');
}

function renderCheckCompanyTab() {
  const selected = state.selectedCheckResult;
  const personResults = selected?.personResults || [];
  const showPersonBlock = state.personAutoLoadingCount > 0 || personResults.length > 0;

  return `
    <div class="flex-1 flex flex-col">
      <div class="mb-8 slide-up">
        <h1 class="text-2xl font-semibold text-text-main mb-2">Поиск</h1>
        <p class="text-text-secondary">Сведения о компании, руководителях и факторах риска</p>
      </div>

      <div class="grid grid-cols-3 gap-6">
        <div class="col-span-2">
          <div class="bg-card rounded-2xl shadow-soft p-8 slide-up" style="animation-delay: 0.1s">
            <h2 class="text-xl font-semibold text-text-main mb-6">Форма проверки</h2>
            <form id="check-company-form" class="space-y-6">
              <div>
                <label for="company-name-inn" class="block text-sm font-medium text-text-main mb-2">
                  ИНН компании или ИП <span class="text-text-secondary text-xs">(в приоритете)</span>
                </label>
                <input
                  type="text"
                  id="company-name-inn"
                  placeholder="10 цифр для компании или 12 цифр для ИП"
                  inputmode="numeric"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all"
                />
              </div>
              <div>
                <label for="company-search-query" class="block text-sm font-medium text-text-main mb-2">
                  Поиск организации <span class="text-text-secondary text-xs">(если не указан ИНН)</span>
                </label>
                <div class="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    id="company-search-query"
                    placeholder="Например: пао ростелеком"
                    class="input-field flex-1 px-4 py-3 rounded-xl focus:outline-none transition-all"
                  />
                  <select
                    id="company-search-type"
                    class="input-field px-3 py-3 rounded-xl focus:outline-none transition-all bg-surface text-text-main border border-card-border"
                  >
                    <option value="auto">тип: авто</option>
                    <option value="name">наименование</option>
                    <option value="founder-name">ФИО учредителя</option>
                    <option value="leader-name">ФИО руководителя</option>
                    <option value="okved">ОКВЭД</option>
                    <option value="reg-date">дата регистрации</option>
                    <option value="upd-date">дата обновления</option>
                    <option value="phone">телефон</option>
                    <option value="email">email</option>
                  </select>
                </div>
                <p class="text-xs text-text-secondary mt-2 leading-relaxed">
                  Можно ввести: наименование, ФИО учредителя (prefix <code class="text-text-main">founder:</code>),
                  ФИО руководителя (<code class="text-text-main">leader:</code>), код ОКВЭД (62, 62.01, 62.01.1, 62.01.11),
                  дату (ГГГГ-ММ-ДД), телефон или email. Тип можно выбрать вручную в списке рядом.
                  Если заполнен ИНН — поиск идёт по нему.
                </p>
              </div>
              <button
                type="submit"
                class="w-full px-6 py-3 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl transition-all shadow-soft"
              >
                <i data-lucide="search" class="w-5 h-5 inline mr-2"></i>
                Проверить
              </button>
            </form>
          </div>
        </div>

        <div class="col-span-1">
          <div class="bg-primary/[.10] rounded-2xl p-6 slide-up" style="animation-delay: 0.2s">
            <div class="flex items-start gap-3">
              <i data-lucide="info" class="w-5 h-5 text-primary mt-1 shrink-0"></i>
              <div>
                <h3 class="font-semibold text-text-main mb-2">О проверке</h3>
                <p class="text-sm text-text-secondary">
                  Получаем реквизиты, статус и факторы риска. Руководители и учредители проверяются автоматически.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-8" id="company-search-results">
        ${state.companySearchLoading ? `
          <div class="bg-card rounded-2xl shadow-soft p-6 slide-up">
            <div class="flex items-center gap-3">
              <div class="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
              <p class="text-sm text-text-secondary">Ищем организации…</p>
            </div>
          </div>
        ` : ''}
        ${!state.companySearchLoading && state.companySearchError ? `
          <div class="bg-card rounded-2xl shadow-soft p-6 slide-up border border-red-800/40">
            <div class="flex items-start gap-3">
              <i data-lucide="alert-circle" class="w-5 h-5 text-red-400 shrink-0 mt-0.5"></i>
              <div>
                <h3 class="text-sm font-semibold text-text-main mb-1">Ошибка поиска</h3>
                <p class="text-sm text-text-secondary">${escapeHtml(state.companySearchError)}</p>
              </div>
            </div>
          </div>
        ` : ''}
        ${!state.companySearchLoading && state.companySearchResults?.length ? `
          <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up">
            <div class="p-6 border-b border-card-border flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 class="text-lg font-semibold text-text-main">Найденные организации</h2>
                <p class="text-sm text-text-secondary mt-1">
                  Запрос: «${escapeHtml(state.companySearchQueryLabel || '')}» ·
                  показано ${state.companySearchResults.length} записей
                  ${state.companySearchTotalPages
                    ? `· страница ${state.companySearchPage} из ${state.companySearchTotalPages}`
                    : ''}
                </p>
              </div>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  id="company-search-prev"
                  class="px-3 py-1.5 rounded-lg text-xs bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all disabled:opacity-40"
                  ${state.companySearchPage <= 1 ? 'disabled' : ''}
                >
                  ← Назад
                </button>
                <button
                  type="button"
                  id="company-search-next"
                  class="px-3 py-1.5 rounded-lg text-xs bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all disabled:opacity-40"
                  ${!state.companySearchTotalPages || state.companySearchPage >= state.companySearchTotalPages ? 'disabled' : ''}
                >
                  Далее →
                </button>
                <button type="button" id="company-search-clear" class="px-3 py-1.5 rounded-lg text-xs bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all">
                  Скрыть
                </button>
              </div>
            </div>
            ${!state.companySearchTotalPages || state.companySearchTotalPages <= 1 ? '' : ''}
            <div class="divide-y divide-card-border">
              ${state.companySearchResults.map(item => `
                <button
                  type="button"
                  class="company-search-item w-full text-left p-5 hover:bg-[#222222] transition-colors"
                  data-inn="${escapeHtml(item.inn || '')}"
                  data-name="${escapeHtml(item.name || '')}"
                >
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="font-medium text-text-main">${escapeHtml(item.name || '—')}</div>
                      ${item.full_name && item.full_name !== item.name
                        ? `<div class="text-xs text-text-secondary mt-1">${escapeHtml(item.full_name)}</div>`
                        : ''}
                      <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-secondary mt-2">
                        ${item.inn ? `<span>ИНН ${escapeHtml(item.inn)}</span>` : ''}
                        ${item.ogrn ? `<span>ОГРН ${escapeHtml(item.ogrn)}</span>` : ''}
                        ${item.registration_date ? `<span>рег. ${escapeHtml(item.registration_date)}</span>` : ''}
                        ${item.okved ? `<span>ОКВЭД ${escapeHtml(item.okved)}</span>` : ''}
                      </div>
                      ${item.address ? `<div class="text-xs text-text-secondary mt-1">${escapeHtml(item.address)}</div>` : ''}
                    </div>
                    <div class="flex flex-col items-end gap-2">
                      ${item.status ? `
                        <span class="px-2 py-1 rounded-lg text-xs ${
                          String(item.status).toLowerCase().includes('действ')
                            ? 'bg-green-900/[.30] text-green-400'
                            : 'bg-amber-900/[.30] text-amber-400'
                        }">${escapeHtml(item.status)}</span>
                      ` : ''}
                      <span class="text-xs text-primary">Проверить →</span>
                    </div>
                  </div>
                </button>
              `).join('')}
            </div>
          </div>
        ` : ''}
        ${!state.companySearchLoading && state.companySearchEmpty ? `
          <div class="bg-card rounded-2xl shadow-soft p-6 slide-up">
            <p class="text-sm text-text-secondary">Ничего не найдено. Уточните запрос или измените тип поиска.</p>
          </div>
        ` : ''}
      </div>

      <div class="mt-8 space-y-6" id="check-result-area">
        <!-- Компания -->
        <div id="company-module">
          ${state.moduleLoading?.company || state.checkLoading
            ? `<div class="bg-card rounded-2xl shadow-soft p-6">${moduleHeader('Компания', { loading: true, subtitle: 'Загружаем сведения…' })}</div>`
            : selected?.company
              ? renderCheckResultHTML(selected.company, selected)
              : state.checkError
                ? renderCheckErrorHTML(state.checkError)
                : ''}
        </div>

        <!-- Финансы -->
        <div id="finances-area">
          ${state.moduleLoading?.finances
            ? `<div class="bg-card rounded-2xl shadow-soft p-6">${moduleHeader('Финансовая отчетность', { loading: true })}</div>`
            : state.companyFinances
              ? renderFinancesHTML(state.companyFinances)
              : state.companyFinancesError
                ? renderFinancesErrorHTML(state.companyFinancesError)
                : ''}
        </div>

        <!-- Анализ рынка -->
        <div id="market-area-wrap">
          ${state.moduleLoading?.market && !marketState.loading
            ? `<div class="bg-card rounded-2xl shadow-soft p-6">${moduleHeader('Анализ рынка и конкурентов', { loading: true })}</div>`
            : renderMarketSummaryHTML(marketState.summary, {
                companyName: selected?.company?.name || selected?.company?.full_name || selected?.name,
                inn: selected?.company?.inn || selected?.inn,
              })}
        </div>

        <!-- История событий -->
        <div id="timeline-area">
          ${state.moduleLoading?.timeline
            ? `<div class="bg-card rounded-2xl shadow-soft p-6">${moduleHeader('История событий', { loading: true })}</div>`
            : state.companyTimeline
              ? renderTimelineHTML(state.companyTimeline, state.timelineExpanded)
              : state.companyTimelineError
                ? renderTimelineErrorHTML(state.companyTimelineError)
                : ''}
        </div>

        <!-- Реестры -->
        <div class="space-y-6" id="registries-area">
          ${REGISTRY_SECTIONS.map(section => {
            const loading = !!state.moduleLoading?.[`reg_${section.key}`];
            const data = state.companyRegistries?.[section.key];
            const error = state.companyRegistries?.[`${section.key}_error`];
            const id = `registry-card-${section.key}`;
            if (loading) {
              return `<div class="bg-card rounded-2xl shadow-soft p-6" id="${escapeHtml(id)}">${moduleHeader(section.title, { subtitle: section.subtitle, loading: true })}</div>`;
            }
            if (error && !data) return renderRegistryErrorHTML(id, section.title, error);
            return renderRegistrySection({
              id,
              title: section.title,
              subtitle: section.subtitle,
              items: (data && data.items) || [],
              expandKey: section.key,
              expanded: !!state.registryExpanded?.[section.key],
              note: data?.partialError || null,
            });
          }).join('')}
        </div>

        <!-- Физлица -->
        <div class="slide-up" id="persons-module">
          ${state.moduleLoading?.persons
            ? `<div class="bg-card rounded-2xl shadow-soft p-6">${moduleHeader('Деловые связи физлиц', { loading: true, subtitle: 'Автопроверка руководителей и учредителей' })}</div>`
            : showPersonBlock ? `
            <details class="group bg-card rounded-2xl shadow-soft overflow-hidden" ${state.personResultsExpanded ? 'open' : ''}>
              <summary class="cursor-pointer select-none p-5 flex items-center justify-between gap-3 hover:bg-[#222222] transition-colors">
                <div class="flex items-center gap-3">
                  <i data-lucide="users" class="w-5 h-5 text-primary shrink-0"></i>
                  <div>
                    <h2 class="text-base font-semibold text-text-main">Деловые связи физлиц</h2>
                    <p class="text-xs text-text-secondary mt-0.5">
                      Автопроверка руководителей и учредителей
                      ${personResults.length ? ` · ${personResults.length}` : ''}
                    </p>
                  </div>
                </div>
                <i data-lucide="chevron-down" class="w-4 h-4 text-text-secondary shrink-0 transition-transform group-open:rotate-180"></i>
              </summary>
              <div class="px-5 pb-5 space-y-4 border-t border-card-border pt-4">
                ${(() => {
                  const summary = personCoverageSummary(personResults);
                  const remaining = personResults.filter(p => p.inn && (p.checkStatus === 'not_checked' || p.checkStatus === 'error'));
                  return `
                    <div class="flex flex-wrap items-center justify-between gap-3">
                      <p class="text-sm text-text-secondary">${escapeHtml(summary.text)}</p>
                      ${remaining.length ? `
                        <button
                          type="button"
                          id="person-check-rest"
                          class="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm rounded-xl font-medium transition-all"
                        >
                          Проверить остальных (${remaining.length})
                        </button>
                      ` : ''}
                    </div>
                  `;
                })()}
                ${renderPersonResultsList(personResults)}
              </div>
            </details>
          ` : ''}
        </div>
      </div>

      <div class="mt-8 slide-up" style="animation-delay: 0.3s">
        <div class="bg-card rounded-2xl shadow-soft overflow-hidden">
          <div class="p-6 border-b border-card-border">
            <h2 class="text-xl font-semibold text-text-main">История оценки</h2>
            <p class="text-sm text-text-secondary mt-1">Выберите запись, чтобы снова показать компанию и связанных физлиц</p>
          </div>
          <div class="divide-y divide-card-border">
            ${renderCompanyHistoryList()}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderCheckPersonTab() {
  const selected = state.selectedPersonResult;

  return `
    <div class="flex-1 flex flex-col">
      <div class="mb-8 slide-up">
        <h1 class="text-2xl font-semibold text-text-main mb-2">Проверить физ. лицо</h1>
        <p class="text-text-secondary">Деловые связи, ИП и факторы риска по ИНН физического лица</p>
      </div>

      <div class="grid grid-cols-3 gap-6">
        <div class="col-span-2">
          <div class="bg-card rounded-2xl shadow-soft p-8 slide-up" style="animation-delay: 0.1s">
            <h2 class="text-xl font-semibold text-text-main mb-6">Поиск физического лица</h2>
            <form id="person-check-form" class="flex flex-col sm:flex-row gap-3 sm:items-end">
              <div class="flex-1">
                <label for="person-inn" class="block text-sm font-medium text-text-main mb-2">
                  ИНН физического лица <span class="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  id="person-inn"
                  placeholder="12 цифр"
                  inputmode="numeric"
                  maxlength="12"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all"
                  required
                />
              </div>
              <button
                type="submit"
                class="px-6 py-3 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl transition-all shadow-soft whitespace-nowrap"
              >
                <i data-lucide="user-search" class="w-5 h-5 inline mr-2"></i>
                Проверить физлицо
              </button>
            </form>
          </div>
        </div>

        <div class="col-span-1">
          <div class="bg-primary/[.10] rounded-2xl p-6 slide-up" style="animation-delay: 0.2s">
            <div class="flex items-start gap-3">
              <i data-lucide="info" class="w-5 h-5 text-primary mt-1 shrink-0"></i>
              <div>
                <h3 class="font-semibold text-text-main mb-2">О проверке</h3>
                <p class="text-sm text-text-secondary">
                  Организации, ИП, товарные знаки, банкротства и факторы риска физлица.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-8" id="person-result-area">
        ${state.personCheckLoading
          ? renderPersonLoadingHTML()
          : selected?.person
            ? renderPersonResultHTML(selected.person, selected)
            : state.personCheckError
              ? renderPersonErrorHTML(state.personCheckError)
              : ''}
      </div>

      <div class="mt-8 slide-up" style="animation-delay: 0.3s">
        <div class="bg-card rounded-2xl shadow-soft overflow-hidden">
          <div class="p-6 border-b border-card-border">
            <h2 class="text-xl font-semibold text-text-main">История проверок физлиц</h2>
          </div>
          <div class="divide-y divide-card-border">
            ${(() => {
              const history = state.personCheckHistory || [];
              if (history.length === 0) {
                return '<div class="p-6 text-center text-text-secondary">История пуста. Начните с первой проверки.</div>';
              }
              return history.map(record => {
                const active = selected?.id === record.id;
                return `
                  <div
                    class="p-6 hover:bg-[#222222] transition-colors ${record.person ? 'cursor-pointer person-history-item' : ''} ${active ? 'bg-[#222222]' : ''}"
                    ${record.person ? `data-person-id="${escapeHtml(record.id)}"` : ''}
                  >
                    <div class="flex items-start justify-between mb-2">
                      <div class="flex-1">
                        <h3 class="font-semibold text-text-main">${escapeHtml(record.name)}</h3>
                        <p class="text-sm text-text-secondary mt-1">ИНН: ${escapeHtml(record.inn)}</p>
                      </div>
                      <span class="px-3 py-1 rounded-full text-xs font-medium ${
                        record.status === 'Анализ завершен'
                          ? 'bg-green-900/[.30] text-green-400'
                          : record.status === 'Ошибка проверки'
                            ? 'bg-red-900/[.30] text-red-400'
                            : 'bg-amber-900/[.30] text-amber-400'
                      }">
                        ${escapeHtml(record.status)}
                      </span>
                    </div>
                    <div class="flex items-center gap-4 text-sm">
                      <span class="text-text-secondary">Запрошено: ${formatDate(record.requestedAt)}</span>
                      ${record.riskLevel ? `<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">Риск: ${escapeHtml(record.riskLevel)}</span>` : ''}
                    </div>
                    ${record.findings ? `<p class="text-sm text-text-secondary whitespace-pre-line mt-2">${escapeHtml(record.findings)}</p>` : ''}
                  </div>
                `;
              }).join('');
            })()}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderPostContent() {
  switch (state.currentPostTab) {
    case 'portfolio':   return renderPortfolioDashboard();
    case 'companies':   return renderCompanies();
    case 'obligations': return renderObligations();
    case 'assistant':   return renderAiAssistant();
    default:            return renderPortfolioDashboard();
  }
}

function renderFunnelContent() {
  if (state.currentFundTab === 'projects') return renderProjectsTab();
  if (state.currentFundTab === 'pitch-decks') return renderPitchDeckTab();
  // check-person / competency hidden from nav — always render search as fallback
  return renderCheckCompanyTab();
}

function renderArchiveContent() {
  return `
    <div class="flex-1 flex flex-col items-center justify-center gap-4 slide-up">
      <div class="w-20 h-20 rounded-2xl bg-card border border-card-border flex items-center justify-center">
        <i data-lucide="archive" class="w-9 h-9 text-text-secondary"></i>
      </div>
      <div class="text-center">
        <h2 class="text-xl font-semibold text-text-main mb-2">Архив</h2>
        <p class="text-text-secondary text-sm max-w-xs">Здесь будут отображаться завершённые и закрытые сделки. Раздел в разработке.</p>
      </div>
    </div>
  `;
}

export function renderFundDashboard() {
  // Hidden tabs (person/competency) — fall back to search if stale state.
  const tab = ['projects', 'check-company', 'pitch-decks'].includes(state.currentFundTab)
    ? state.currentFundTab
    : 'check-company';
  if (state.currentFundTab !== tab) state.currentFundTab = tab;
  return `
    <div class="min-h-screen bg-surface flex flex-col">
      ${renderHeader()}
      <div class="flex-1 flex overflow-hidden">
        ${renderFundSidebar()}
        <main class="flex-1 px-6 sm:px-8 lg:px-10 py-8 overflow-y-auto">
          ${state.fundPhase === 'funnel' ? renderFunnelContent()
          : state.fundPhase === 'portfolio' ? renderPostContent()
          : state.fundPhase === 'weak-signals' ? renderWeakSignalsTab()
          : renderArchiveContent()}
        </main>
      </div>
      ${renderNotificationsHTML()}
    </div>
  `;
}
