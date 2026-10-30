import { state } from '../state.js';
import {
  allTrends,
  excludedItems,
  filterTrendsByQuery,
  sourceById,
  trendById,
  trendTrust,
} from '../data/weakSignals.js';
import { renderKnowledgeSignalsHTML } from './knowledge.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

/** Лупа из TechTrendSearcher, светло-серая под тёмную тему MacroMindAnalytics. */
function renderSearchScene() {
  return `
    <svg class="w-full max-w-[280px] h-auto" viewBox="0 0 420 360" role="img" aria-label="Поиск слабых сигналов">
      <defs>
        <linearGradient id="ws-g" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#E8E8E8" />
          <stop offset="1" stop-color="#B8B8B8" />
        </linearGradient>
        <filter id="ws-soft">
          <feDropShadow dx="0" dy="18" stdDeviation="12" flood-color="#000000" flood-opacity="0.35" />
        </filter>
      </defs>
      <ellipse cx="210" cy="300" rx="110" ry="18" fill="#F0F0F0" opacity="0.08" />
      <g filter="url(#ws-soft)">
        <circle cx="168" cy="150" r="62" fill="url(#ws-g)" />
        <circle cx="168" cy="150" r="34" fill="#2C2C2C" />
        <rect x="214" y="196" width="86" height="24" rx="12" transform="rotate(42 214 196)" fill="url(#ws-g)" />
        <circle cx="300" cy="108" r="16" fill="#C8E6D0" />
        <circle cx="328" cy="168" r="12" fill="#68B589" />
        <circle cx="112" cy="92" r="10" fill="#C8E6D0" />
      </g>
    </svg>
  `;
}

function kindBadge(kind) {
  if (kind === 'хайп') return '<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">хайп</span>';
  if (kind === 'на слуху') return '<span class="px-2 py-1 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">на слуху</span>';
  return '<span class="px-2 py-1 rounded-lg text-xs bg-green-900/[.30] text-green-400">ранний сигнал</span>';
}

function trustBadge(trust) {
  if (trust === 'высокий') return '<span class="px-2 py-1 rounded-lg text-xs bg-green-900/[.30] text-green-400">доверие высокое</span>';
  if (trust === 'средний') return '<span class="px-2 py-1 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">доверие среднее</span>';
  return '<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">доверие низкое</span>';
}

function statusBadge(status) {
  if (status === 'supported') return '<span class="px-2 py-1 rounded-lg text-xs bg-green-900/[.30] text-green-400">подтверждено</span>';
  if (status === 'unsupported') return '<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">не подтверждено</span>';
  return '<span class="px-2 py-1 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">гипотеза</span>';
}

function sparkline(values) {
  const max = Math.max(...(values || [1]), 1);
  const w = 120;
  const h = 40;
  const step = values && values.length > 1 ? w / (values.length - 1) : w;
  const points = (values || [])
    .map((v, i) => `${i * step},${h - (v / max) * (h - 6) - 3}`)
    .join(' ');
  return `
    <svg viewBox="0 0 ${w} ${h}" class="w-[120px] h-10" aria-hidden="true">
      <polyline fill="none" stroke="#68B589" stroke-width="2" points="${points}" />
    </svg>
  `;
}

function renderTrendRow(trend, index) {
  const trust = trendTrust(trend);
  return `
    <button
      type="button"
      class="weak-signal-card w-full text-left bg-surface rounded-xl p-5 border border-card-border hover:border-primary/50 hover:bg-[#222222] transition-all cursor-pointer"
      data-trend-id="${escapeHtml(trend.id)}"
    >
      <div class="flex flex-col sm:flex-row gap-4">
        <div class="text-sm font-semibold text-text-secondary w-8 shrink-0">${String(index + 1).padStart(2, '0')}</div>
        <div class="flex-1 min-w-0">
          <h3 class="text-base font-semibold text-text-main">${escapeHtml(trend.name)}</h3>
          <p class="text-sm text-text-secondary mt-2">${escapeHtml(trend.definition)}</p>
          <ul class="mt-3 space-y-1">
            ${(trend.reasons || []).slice(0, 3).map(r => `
              <li class="text-xs text-text-secondary flex items-start gap-2">
                <span class="text-primary mt-0.5">•</span>
                <span>${escapeHtml(r)}</span>
              </li>
            `).join('')}
          </ul>
          <div class="flex flex-wrap items-center gap-2 mt-3">
            ${kindBadge(trend.kind)}
            ${trustBadge(trust)}
          </div>
        </div>
        <div class="text-right shrink-0">
          <div class="text-2xl font-bold text-primary">${escapeHtml(trend.signal)}%</div>
          <div class="text-xs text-text-secondary mt-1">уверенность модели</div>
        </div>
      </div>
    </button>
  `;
}

function renderExcludedList() {
  return `
    <div class="space-y-3">
      ${excludedItems.map(item => `
        <div class="bg-surface rounded-xl p-5 border border-card-border">
          <div class="flex flex-wrap gap-2">
            ${item.kind === 'зрелое' ? '<span class="px-2 py-1 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">зрелое</span>' : ''}
            ${item.kind === 'хайп' ? '<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">хайп</span>' : ''}
            ${item.kind === 'шум' ? '<span class="px-2 py-1 rounded-lg text-xs bg-red-900/[.30] text-red-400">шум</span>' : ''}
          </div>
          <h4 class="text-base font-semibold text-text-main mt-3">${escapeHtml(item.name)}</h4>
          <p class="text-sm text-text-secondary mt-2">${escapeHtml(item.reason)}</p>
        </div>
      `).join('')}
    </div>
  `;
}

function renderProgress() {
  const steps = state.weakSignalsProgress?.steps || [];
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6" id="weak-signals-progress">
      <p class="text-xs text-text-secondary uppercase tracking-wider">Прогресс задачи</p>
      <h3 class="text-lg font-semibold text-text-main mt-2">${escapeHtml(state.weakSignalsQuery || '')}</h3>
      <p class="text-sm text-text-secondary mt-2">Сбор и проверка открытых источников.</p>
      <div class="mt-6 space-y-3">
        ${steps.map((step, index) => {
          const active = index < (state.weakSignalsProgress?.done || 0);
          return `
            <div class="flex items-center gap-4">
              <div class="flex-1">
                <div class="text-sm font-medium text-text-main">${escapeHtml(step.title)}</div>
                <div class="text-xs text-text-secondary mt-1">${escapeHtml(active ? step.count : 'ожидает')}</div>
              </div>
              <div class="w-40 h-2 bg-[#383838] rounded-full overflow-hidden">
                <div class="h-full bg-primary rounded-full transition-all duration-500" style="width: ${active ? '100%' : '12%'}"></div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderSignalCard(trend) {
  if (!trend) return '';
  const problem = (trend.claims || []).find(c => c.label === 'Проблема');
  const advantage = (trend.claims || []).find(c => c.label === 'Преимущество');
  const usecase = (trend.claims || []).find(c => c.label === 'Кейс');
  const values = [
    trend.features?.shareGrowth,
    trend.features?.novelty,
    trend.features?.orgs,
    trend.features?.hhi,
    trend.features?.nT,
  ];
  const featureRows = [
    ['Рост доли', 'главный предиктор раннего сигнала', n => Number(n).toFixed(2)],
    ['Новизна', 'max(0; 1 − возраст / 10)', n => Number(n).toFixed(2)],
    ['Организации', 'независимые аффилиации', n => String(n)],
    ['HHI', 'концентрация, чем ниже — тем лучше', n => Number(n).toFixed(2)],
    ['n_T', 'работы в год решения', n => String(n)],
  ];

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden" id="weak-signal-card">
      <div class="p-6 border-b border-card-border">
        <button type="button" id="weak-signal-back" class="inline-flex items-center gap-2 text-sm text-primary hover:underline mb-4">
          ← Назад к выдаче
        </button>
        <p class="text-xs text-text-secondary">Запрос: «${escapeHtml(state.weakSignalsQuery)}» · отчёт по сигналу</p>
        <h2 class="text-2xl font-semibold text-text-main mt-2">${escapeHtml(trend.name)}</h2>
        <p class="text-text-secondary mt-3">${escapeHtml(trend.definition)}</p>
        <div class="flex flex-wrap gap-2 mt-4">
          ${trustBadge(trendTrust(trend))}
          ${kindBadge(trend.kind)}
        </div>
      </div>

      <div class="p-6 space-y-8">
        <section>
          <h3 class="text-lg font-semibold text-text-main">Уверенность модели ${escapeHtml(trend.signal)}%</h3>
          <p class="text-sm text-text-secondary mt-2">
            Вероятность слабого сигнала по модели. Не прогноз рыночного успеха.
            Ранг среди направления: ${escapeHtml(trend.signal)} из 100.
          </p>
          <div class="mt-4">${sparkline(trend.series)}</div>
          <p class="text-xs text-text-secondary mt-2">
            Первое найденное упоминание: ${escapeHtml(trend.firstYear)}.
          </p>
        </section>

        <section>
          <h3 class="text-base font-semibold text-text-main mb-2">Описание технологии</h3>
          <p class="text-sm text-text-secondary">${escapeHtml(trend.definition)}</p>
          ${problem ? `<p class="text-sm text-text-secondary mt-3">${escapeHtml(problem.text)}</p>` : ''}
        </section>

        <section>
          <h3 class="text-base font-semibold text-text-main mb-2">Потенциальное преимущество</h3>
          <p class="text-sm text-text-secondary">${escapeHtml(advantage?.text || '')}</p>
          ${advantage ? `<div class="mt-2">${statusBadge(advantage.status)}</div>` : ''}
        </section>

        <section>
          <h3 class="text-base font-semibold text-text-main mb-2">Кейс-пример</h3>
          <p class="text-sm text-text-secondary">${escapeHtml(usecase?.text || '')}</p>
          ${usecase ? `<div class="mt-2">${statusBadge(usecase.status)}</div>` : ''}
        </section>

        <section>
          <h3 class="text-base font-semibold text-text-main mb-2">Почему это слабый сигнал</h3>
          <ul class="space-y-2">
            ${(trend.reasons || []).map(r => `
              <li class="text-sm text-text-secondary flex items-start gap-2">
                <span class="text-primary mt-0.5">•</span>
                <span>${escapeHtml(r)}</span>
              </li>
            `).join('')}
          </ul>
          <table class="w-full mt-4 text-sm">
            <tbody>
              ${featureRows.map((row, i) => `
                <tr class="border-t border-card-border">
                  <td class="py-2 pr-4">
                    <div class="font-medium text-text-main">${escapeHtml(row[0])}</div>
                    <div class="text-xs text-text-secondary">${escapeHtml(row[1])}</div>
                  </td>
                  <td class="py-2 text-text-main text-right">${escapeHtml(row[2](values[i]))}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </section>

        <section>
          <h3 class="text-base font-semibold text-text-main mb-3">Источники</h3>
          <div class="space-y-3">
            ${(trend.sources || []).map(s => `
              <div class="bg-surface rounded-xl p-4 border border-card-border">
                <a href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer" class="text-sm font-medium text-primary hover:underline">
                  ${escapeHtml(s.title)}
                </a>
                <p class="text-xs text-text-secondary mt-2">${escapeHtml(s.summaryRu)}${s.generated ? ' · сгенерированное резюме' : ''}</p>
                <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary mt-2">
                  <span>${escapeHtml(s.date)}</span>
                  <span>${escapeHtml(s.type)}</span>
                  <span>${escapeHtml(s.language)}</span>
                  <span>${escapeHtml(s.trust)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </section>

        ${(trend.claims || []).filter(c => c.status === 'supported' && c.sourceId).map(claim => {
          const source = sourceById(trend, claim.sourceId);
          if (!source) return '';
          return `
            <section class="bg-surface rounded-xl p-4 border border-card-border">
              <h4 class="text-xs uppercase tracking-wider text-text-secondary">${escapeHtml(claim.label)}: цитата</h4>
              <p class="text-sm text-text-main mt-2 italic">«${escapeHtml(source.quote)}»</p>
              <p class="text-xs text-text-secondary mt-2">
                Язык оригинала: ${escapeHtml(source.language)} ·
                <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer" class="text-primary hover:underline">первоисточник</a>
              </p>
            </section>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderResults() {
  const view = state.weakSignalsView || 'results';
  const selectedId = state.weakSignalsSelectedId;

  if (selectedId) {
    const trend = trendById(selectedId);
    return renderSignalCard(trend);
  }

  const matched = filterTrendsByQuery(state.weakSignalsQuery || '', allTrends);
  const highConfidence = matched.filter(t => t.signal >= 75).length;

  return `
    <div id="weak-signals-results">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <p class="text-xs text-text-secondary uppercase tracking-wider">Открытый поиск · выдача</p>
          <h2 class="text-xl font-semibold text-text-main mt-2">
            ${view === 'excluded' ? 'Исключённые как не слабый сигнал' : 'Слабые сигналы по направлению'}
          </h2>
          <p class="text-sm text-text-secondary mt-2 max-w-2xl">
            ${view === 'excluded'
              ? 'Зрелые тренды, массовое внедрение, отраслевые стандарты, хайп и шум в выдачу не входят.'
              : `Запрос: «${escapeHtml(state.weakSignalsQuery)}» · найдено: ${matched.length}`}
          </p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button
            type="button"
            class="weak-signals-view-btn px-4 py-2 rounded-xl text-sm font-medium border transition-all ${view === 'results' ? 'bg-primary text-white border-primary' : 'bg-card border-[#484848] text-text-secondary hover:text-text-main'}"
            data-view="results"
          >
            Выдача
          </button>
          <button
            type="button"
            class="weak-signals-view-btn px-4 py-2 rounded-xl text-sm font-medium border transition-all ${view === 'excluded' ? 'bg-primary text-white border-primary' : 'bg-card border-[#484848] text-text-secondary hover:text-text-main'}"
            data-view="excluded"
          >
            Исключённые
          </button>
        </div>
      </div>

      ${view === 'results' ? (matched.length ? `
        <div class="grid grid-cols-3 gap-4 mb-6">
          <div class="bg-card rounded-2xl shadow-soft p-5">
            <div class="text-2xl font-bold text-text-main">${matched.length}</div>
            <p class="text-sm text-text-secondary mt-2">сигналов по запросу</p>
          </div>
          <div class="bg-card rounded-2xl shadow-soft p-5">
            <div class="text-2xl font-bold text-text-main">${allTrends.length}</div>
            <p class="text-sm text-text-secondary mt-2">всего в корпусе анализа</p>
          </div>
          <div class="bg-card rounded-2xl shadow-soft p-5">
            <div class="text-2xl font-bold text-text-main">${highConfidence}</div>
            <p class="text-sm text-text-secondary mt-2">с уверенностью выше 75%</p>
          </div>
        </div>
        <div class="space-y-3">
          ${matched.map((trend, index) => renderTrendRow(trend, index)).join('')}
        </div>
      ` : `
        <div class="bg-card rounded-2xl shadow-soft p-8 text-center">
          <i data-lucide="search-x" class="w-10 h-10 text-text-secondary mx-auto mb-3"></i>
          <h3 class="text-lg font-semibold text-text-main mb-2">Слабых сигналов не найдено</h3>
          <p class="text-sm text-text-secondary max-w-md mx-auto">
            По запросу «${escapeHtml(state.weakSignalsQuery)}» в корпусе анализа нет совпадений.
            Уточните направление или попробуйте смежную формулировку.
          </p>
        </div>
      `) : renderExcludedList()}
    </div>
  `;
}

export function renderWeakSignalsTab() {
  const chips = [
    'технологии в ИИ',
    'перспективные решения в финтехе',
    'слабые сигналы в области кибербезопасности',
  ];
  const phase = state.weakSignalsPhase || 'idle';
  const error = state.weakSignalsError || '';
  // Only animate on first paint of the tab — not on every progress tick (flicker).
  const anim = phase === 'idle' && !state.weakSignalsQuery ? 'slide-up' : '';

  return `
    <div class="flex-1 flex flex-col">
      <div class="mb-8 ${anim}">
        <h1 class="text-2xl font-semibold text-text-main mb-2">Поиск слабых сигналов</h1>
        <p class="text-text-secondary">Ранние технологические сигналы по направлению из открытых источников</p>
      </div>

      <div class="grid grid-cols-3 gap-6 mb-8">
        <div class="col-span-2 bg-card rounded-2xl shadow-soft p-8 ${anim}">
          <h2 class="text-xl font-semibold text-text-main">Слабые сигналы по направлению</h2>
          <p class="text-sm text-text-secondary mt-2">Введите запрос в свободной форме.</p>
          <form id="weak-signals-form" class="mt-6 flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              id="weak-signals-query"
              placeholder="технологии в ИИ"
              value="${escapeHtml(state.weakSignalsQuery || '')}"
              class="input-field flex-1 px-4 py-3 rounded-xl focus:outline-none transition-all"
            />
            <button
              type="submit"
              ${phase === 'progress' ? 'disabled' : ''}
              class="px-6 py-3 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl transition-all shadow-soft whitespace-nowrap disabled:opacity-50"
            >
              <i data-lucide="search" class="w-5 h-5 inline mr-2"></i>
              ${phase === 'progress' ? 'Ищем…' : 'Найти сигналы'}
            </button>
          </form>
          ${error ? `<p class="text-sm text-red-400 mt-3">${escapeHtml(error)}</p>` : ''}
          <div class="flex flex-wrap gap-2 mt-4">
            ${chips.map(item => `
              <button
                type="button"
                class="weak-signal-chip px-3 py-1.5 rounded-full text-xs bg-surface border border-card-border text-text-secondary hover:text-text-main hover:border-primary/50 transition-all"
                data-query="${escapeHtml(item)}"
              >
                ${escapeHtml(item)}
              </button>
            `).join('')}
          </div>
        </div>
        <div class="col-span-1 bg-card rounded-2xl shadow-soft p-6 flex items-center justify-center ${anim}" style="animation-delay: 0.1s">
          ${renderSearchScene()}
        </div>
      </div>

      <div class="space-y-6">
        ${phase === 'progress' ? renderProgress() : ''}
        ${phase === 'done' ? renderResults() : ''}
      </div>

      <div class="mt-8">
        ${renderKnowledgeSignalsHTML({
          events: state.knowledgeSignals?.events,
          hypotheses: state.knowledgeSignals?.hypotheses,
          loading: state.knowledgeSignalsLoading,
          error: state.knowledgeSignalsError,
        })}
      </div>
    </div>
  `;
}
