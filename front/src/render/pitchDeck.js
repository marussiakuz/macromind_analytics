import { state } from '../state.js';
import { slideImageUrl } from '../api/pitchDeck.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

const METRIC_LABELS = {
  revenue: 'Выручка',
  expenses: 'Расходы',
  ebitda: 'EBITDA',
  net_profit: 'Чистая прибыль',
  market_tam: 'TAM',
  market_sam: 'SAM',
  market_som: 'SOM',
  market_size: 'Объём рынка',
  market_share: 'Доля рынка',
  customer_share: 'Доля клиента',
  growth_rate: 'Темп роста',
  headcount: 'Сотрудники',
  customers: 'Клиенты',
  investment_ask: 'Запрос инвестиций',
  investment_raised: 'Привлечено',
  valuation: 'Оценка',
};

const STATUS_LABELS = {
  fact: { text: 'Факт', cls: 'bg-green-900/[.35] text-green-400' },
  forecast: { text: 'Прогноз', cls: 'bg-primary/[.18] text-primary' },
  target: { text: 'Цель', cls: 'bg-purple-900/[.35] text-purple-400' },
  unknown: { text: 'Не указано', cls: 'bg-[#383838] text-text-secondary' },
};

const SEVERITY = {
  high: { text: 'Высокий', cls: 'bg-red-900/[.30] text-red-400 border-red-800/50' },
  medium: { text: 'Средний', cls: 'bg-amber-900/[.30] text-amber-400 border-amber-700/50' },
  low: { text: 'Низкий', cls: 'bg-[#383838] text-text-secondary border-card-border' },
};

const ENTITY_LABELS = { organization: 'Организации', person: 'Люди', inn: 'ИНН', ogrn: 'ОГРН' };

export function renderSlideLinks(slides = []) {
  return slides.map(n => `
    <button type="button" class="pd-slide-link text-primary hover:underline text-xs" data-slide="${Number(n)}">слайд ${Number(n)}</button>
  `).join(' ');
}

export function renderFlagsHTML(flags = []) {
  if (!flags.length) {
    return '<p class="text-sm text-text-secondary">Правила ничего не отметили. Это не значит, что рисков нет: проверены только извлечённые цифры и текст.</p>';
  }
  return flags.map(flag => {
    const severity = SEVERITY[flag.severity] || SEVERITY.low;
    return `
      <div class="border rounded-xl p-3 ${severity.cls}">
        <div class="flex items-center justify-between gap-3">
          <strong class="text-sm">${escapeHtml(flag.title)}</strong>
          <span class="text-xs shrink-0">${severity.text}</span>
        </div>
        <p class="text-sm text-text-main mt-1">${escapeHtml(flag.detail)}</p>
        ${flag.slides?.length ? `<div class="mt-1">${renderSlideLinks(flag.slides)}</div>` : ''}
      </div>
    `;
  }).join('');
}

export function renderFactsHTML(facts = []) {
  if (!facts.length) {
    return '<p class="text-sm text-text-secondary">Числовые показатели не найдены. Просмотрите дек вручную.</p>';
  }
  const rows = [...facts]
    .sort((a, b) => a.slide - b.slide)
    .map(fact => {
      const status = STATUS_LABELS[fact.status] || STATUS_LABELS.unknown;
      const label = METRIC_LABELS[fact.metric] || fact.metric;
      return `
        <tr class="border-t border-card-border ${fact.needs_review ? 'opacity-70' : ''}">
          <td class="py-2 pr-3 text-sm text-text-main">${escapeHtml(label)}${fact.entity ? `<div class="text-xs text-text-secondary">${escapeHtml(fact.entity)}</div>` : ''}</td>
          <td class="py-2 pr-3 text-sm font-medium text-text-main whitespace-nowrap">${escapeHtml(`${fact.value_raw} ${fact.unit_raw}`.trim())}</td>
          <td class="py-2 pr-3 text-sm text-text-secondary whitespace-nowrap">${escapeHtml(fact.period_raw || 'не указан')}</td>
          <td class="py-2 pr-3"><span class="px-2 py-0.5 rounded-full text-xs ${status.cls}">${status.text}</span></td>
          <td class="py-2 pr-3 whitespace-nowrap">${renderSlideLinks([fact.slide])}</td>
          <td class="py-2 text-xs ${fact.needs_review ? 'text-amber-400' : 'text-green-400'} whitespace-nowrap">${fact.needs_review ? 'Сверить' : 'Найдено на слайде'}</td>
        </tr>
      `;
    }).join('');
  return `
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead><tr class="text-xs text-text-secondary">
          <th class="pb-2 font-medium">Показатель</th><th class="pb-2 font-medium">Значение</th><th class="pb-2 font-medium">Период</th>
          <th class="pb-2 font-medium">Статус</th><th class="pb-2 font-medium">Источник</th><th class="pb-2 font-medium">Проверка</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

export function renderEntitiesHTML(entities = []) {
  if (!entities.length) {
    return '<p class="text-sm text-text-secondary">В тексте дека имена не найдены.</p>';
  }
  return Object.entries(ENTITY_LABELS).map(([kind, title]) => {
    const items = entities.filter(e => e.kind === kind).slice(0, 25);
    if (!items.length) return '';
    return `
      <div class="mb-3">
        <div class="text-xs text-text-secondary mb-1">${title}</div>
        <div class="flex flex-wrap gap-1">
          ${items.map(e => `<span class="px-2 py-1 rounded-lg bg-[#222222] text-xs text-text-main" title="Слайды: ${escapeHtml((e.slides || []).join(', '))}">${escapeHtml(e.text)}</span>`).join('')}
        </div>
      </div>
    `;
  }).join('');
}

function renderSlidePreview(analysisId, result) {
  const number = state.pitchDeckSlide;
  if (!number) {
    return '<p class="text-sm text-text-secondary">Нажмите на номер слайда рядом с фактом или флагом, чтобы сверить его с источником.</p>';
  }
  const slide = (result.slides || []).find(s => s.number === number);
  if (!slide?.has_image) {
    return `<p class="text-sm text-text-secondary">Для слайда ${number} нет изображения. Текст слайда:</p>
      <pre class="text-xs text-text-main whitespace-pre-wrap mt-2">${escapeHtml(slide?.text || '')}</pre>`;
  }
  return `
    <div class="text-xs text-text-secondary mb-2">Слайд ${number}</div>
    <img src="${escapeHtml(slideImageUrl(analysisId, number))}" alt="Слайд ${number}" class="w-full rounded-lg border border-card-border" />
  `;
}

export function renderAnalysisHTML(record) {
  const result = record?.result;
  if (!result) return '';
  const summary = result.summary;
  return `
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4 mt-4">
      <div class="xl:col-span-2 space-y-4">
        <section class="bg-card border border-card-border rounded-2xl p-5">
          <div class="flex items-center justify-between gap-3 mb-2">
            <h3 class="font-semibold text-text-main">Краткая сводка</h3>
            <span class="text-xs text-text-secondary">${summary?.generated_by === 'llm' ? 'Составлена моделью' : 'Собрана из фактов'}</span>
          </div>
          <p class="text-sm text-text-main leading-relaxed">${escapeHtml(summary?.text || 'Сводка недоступна')}</p>
          ${summary?.note ? `<p class="text-xs text-amber-400 mt-2">${escapeHtml(summary.note)}</p>` : ''}
          <p class="text-xs text-text-secondary mt-2">Все показатели — заявления компании. Их достоверность здесь не проверялась.</p>
        </section>
        <section class="bg-card border border-card-border rounded-2xl p-5">
          <h3 class="font-semibold text-text-main mb-3">Красные флаги <span class="text-text-secondary font-normal">(${(result.red_flags || []).length})</span></h3>
          <div class="space-y-2">${renderFlagsHTML(result.red_flags)}</div>
        </section>
        <section class="bg-card border border-card-border rounded-2xl p-5">
          <h3 class="font-semibold text-text-main mb-3">Факты <span class="text-text-secondary font-normal">(${(result.facts || []).length})</span></h3>
          ${renderFactsHTML(result.facts)}
        </section>
      </div>
      <div class="space-y-4">
        <section class="bg-card border border-card-border rounded-2xl p-5 xl:sticky xl:top-4">
          <h3 class="font-semibold text-text-main mb-3">Исходный слайд</h3>
          ${renderSlidePreview(record.id, result)}
        </section>
        <section class="bg-card border border-card-border rounded-2xl p-5">
          <h3 class="font-semibold text-text-main mb-3">Упомянутые имена</h3>
          ${renderEntitiesHTML(result.entities)}
          <p class="text-xs text-text-secondary">Найдены автоматически и не проверены.</p>
        </section>
        ${(result.limitations || []).length ? `
          <section class="bg-card border border-card-border rounded-2xl p-5">
            <h3 class="font-semibold text-text-main mb-2">Ограничения</h3>
            ${result.limitations.map(l => `<p class="text-xs text-amber-400 mb-1">${escapeHtml(l)}</p>`).join('')}
          </section>
        ` : ''}
      </div>
    </div>
  `;
}

function renderProgress(record) {
  if (record.status === 'failed') {
    return `<p class="text-sm text-red-400 mt-2">${escapeHtml(record.error_message || 'Не удалось обработать файл')}</p>`;
  }
  if (record.status === 'done') return '';
  const total = record.total_slides || 0;
  const done = record.done_slides || 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  return `
    <div class="mt-3">
      <div class="flex justify-between text-xs text-text-secondary mb-1">
        <span>${total ? `Обработано слайдов: ${done} из ${total}` : 'Файл в очереди'}</span><span>${percent}%</span>
      </div>
      <div class="h-1.5 bg-[#222222] rounded-full overflow-hidden"><div class="h-full bg-primary" style="width: ${percent}%"></div></div>
    </div>
  `;
}

export function renderPitchDeckTab() {
  const model = state.pitchDeckModel;
  const unavailable = model && (!model.available || model.model_installed === false);
  const items = state.pitchDeckList || [];
  const active = state.pitchDeckActive;
  return `
    <div class="max-w-7xl mx-auto slide-up">
      <h2 class="text-xl font-semibold text-text-main">Анализ питч-дека</h2>
      <p class="text-sm text-text-secondary mt-1">Факты, красные флаги и краткая сводка. Файл обрабатывается локальной моделью и не покидает этот компьютер.</p>

      <div class="bg-card border border-card-border rounded-2xl p-5 mt-4">
        ${unavailable ? `<p class="text-sm text-amber-400 mb-3">${escapeHtml(model.message || `Модель ${model.model || ''} не установлена в Ollama`)}</p>` : ''}
        <label class="block text-sm text-text-main mb-2" for="pitchdeck-file">Файл PDF или PPTX, до 100 МБ</label>
        <div class="flex flex-wrap items-center gap-3">
          <input id="pitchdeck-file" type="file" accept=".pdf,.pptx" class="text-sm text-text-secondary" />
          <button id="pitchdeck-upload" type="button" class="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50" ${state.pitchDeckUploading ? 'disabled' : ''}>
            ${state.pitchDeckUploading ? 'Загрузка…' : 'Проанализировать'}
          </button>
        </div>
        ${state.pitchDeckError ? `<p class="text-sm text-red-400 mt-2">${escapeHtml(state.pitchDeckError)}</p>` : ''}
      </div>

      ${items.length ? `
        <div class="bg-card border border-card-border rounded-2xl p-5 mt-4">
          <h3 class="font-semibold text-text-main mb-2">Загруженные деки</h3>
          <div class="divide-y divide-card-border">
            ${items.map(item => `
              <div class="py-2">
                <div class="flex items-center justify-between gap-3">
                  <button type="button" class="pd-open text-sm text-left ${active?.id === item.id ? 'text-primary font-semibold' : 'text-text-main hover:text-primary'}" data-id="${escapeHtml(item.id)}">${escapeHtml(item.filename)}</button>
                  <button type="button" class="pd-delete text-xs text-text-secondary hover:text-red-400 shrink-0" data-id="${escapeHtml(item.id)}">Удалить</button>
                </div>
                ${renderProgress(item)}
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${active?.result ? renderAnalysisHTML(active) : ''}
    </div>
  `;
}
