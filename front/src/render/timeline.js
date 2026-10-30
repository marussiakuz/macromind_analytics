const TIMELINE_COLLAPSED_COUNT = 5;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function formatDate(value) {
  if (!value) return '';
  const iso = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}.${iso[2]}.${iso[1]}`;
  return String(value);
}

function sortNewestFirst(events) {
  return [...(events || [])].sort((a, b) => {
    const da = a?.date || '';
    const db = b?.date || '';
    // строки ISO YYYY-MM-DD сравниваются лексикографически; без даты — в конец
    if (!da && !db) return 0;
    if (!da) return 1;
    if (!db) return -1;
    return db.localeCompare(da);
  });
}

function renderEventList(events) {
  return `
    <ol class="relative border-l border-card-border ml-3 space-y-5">
      ${events.map(item => `
        <li class="ml-6">
          <span class="absolute -left-[7px] mt-1.5 w-3 h-3 rounded-full bg-primary border-2 border-card"></span>
          <div class="text-xs text-text-secondary">${escapeHtml(formatDate(item.date) || 'Без даты')}</div>
          <div class="text-sm text-text-main mt-1">${escapeHtml(item.event || 'Событие без описания')}</div>
        </li>
      `).join('')}
    </ol>
  `;
}

/**
 * Блок «История событий» — после финансовой отчетности.
 * Новые события сверху (от конца к началу); видно 5, остальные по кнопке.
 * @param {object} timeline — нормализованный ответ
 * @param {boolean} expanded
 */
export function renderTimelineHTML(timeline, expanded = false) {
  if (!timeline) return '';
  const events = sortNewestFirst(timeline.events);
  const visible = expanded ? events : events.slice(0, TIMELINE_COLLAPSED_COUNT);
  const hiddenCount = events.length - TIMELINE_COLLAPSED_COUNT;

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" id="timeline-card">
      <div class="p-6 border-b border-card-border">
        <h2 class="text-lg font-semibold text-text-main">История событий</h2>
        <p class="text-sm text-text-secondary mt-1">
          Изменения в ЕГРЮЛ/ЕГРИП · ${escapeHtml(timeline.name || timeline.inn || '')}
        </p>
      </div>

      <div class="p-6">
        ${events.length ? `
          ${renderEventList(visible)}
          ${hiddenCount > 0 || expanded ? `
            <div class="mt-5">
              <button
                type="button"
                id="timeline-toggle"
                class="px-4 py-2 rounded-xl text-sm font-medium bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all"
              >
                ${expanded ? 'Свернуть' : `Развернуть ещё ${hiddenCount}`}
              </button>
            </div>
          ` : ''}
        ` : `
          <p class="text-sm text-text-secondary">События и изменения не найдены.</p>
        `}
      </div>
    </div>
  `;
}

export function renderTimelineLoadingHTML() {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-5 slide-up" id="timeline-card">
      <div class="flex items-center gap-3">
        <div class="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
        <p class="text-sm text-text-secondary">Загружаем историю событий…</p>
      </div>
    </div>
  `;
}

export function renderTimelineErrorHTML(message) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-5 slide-up" id="timeline-card">
      <div class="flex items-start gap-3">
        <i data-lucide="alert-circle" class="w-5 h-5 text-amber-400 shrink-0 mt-0.5"></i>
        <div>
          <h3 class="text-sm font-semibold text-text-main">История событий</h3>
          <p class="text-sm text-text-secondary mt-1">${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

export { TIMELINE_COLLAPSED_COUNT, sortNewestFirst };
