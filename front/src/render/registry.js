const COLLAPSED_COUNT = 5;

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

function formatMoney(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return `${n.toLocaleString('ru-RU')} ₽`;
}

function renderRow(item) {
  const extra = Object.entries(item.fields || {})
    .filter(([, v]) => v != null && v !== '')
    .map(([label, val]) => `
      <div class="text-xs text-text-secondary">
        <span class="text-text-secondary">${escapeHtml(label)}:</span>
        ${escapeHtml(typeof val === 'number' ? val.toLocaleString('ru-RU') : val)}
      </div>
    `).join('');
  const amount = formatMoney(item.amount);
  return `
    <div class="bg-surface rounded-xl p-4 border border-card-border">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm font-medium text-text-main">${escapeHtml(item.title || '—')}</div>
          <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-secondary mt-1">
            ${item.date ? `<span>${escapeHtml(formatDate(item.date))}</span>` : ''}
            ${item.status ? `<span>${escapeHtml(item.status)}</span>` : ''}
            ${amount ? `<span>${escapeHtml(amount)}</span>` : ''}
          </div>
          ${extra ? `<div class="mt-2 space-y-0.5">${extra}</div>` : ''}
        </div>
        ${item.url ? `
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer"
            class="text-xs text-primary hover:underline shrink-0">Открыть источник</a>
        ` : ''}
      </div>
    </div>
  `;
}

/**
 * Универсальный блок реестра: первые 5 строк, остальные по кнопке.
 * @param {object} opts
 * @param {string} opts.id — id секции (registry-card-*)
 * @param {string} opts.title
 * @param {string} opts.subtitle
 * @param {object[]} opts.items
 * @param {string} opts.expandKey — ключ состояния раскрытия
 * @param {boolean} opts.expanded
 * @param {string|null} opts.note
 */
export function renderRegistrySection({
  id,
  title,
  subtitle,
  items = [],
  expandKey,
  expanded = false,
  note = null,
}) {
  const visible = expanded ? items : items.slice(0, COLLAPSED_COUNT);
  const hiddenCount = Math.max(0, items.length - COLLAPSED_COUNT);

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" id="${escapeHtml(id)}">
      <div class="p-6 border-b border-card-border">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-text-main">${escapeHtml(title)}</h2>
            ${subtitle ? `<p class="text-sm text-text-secondary mt-1">${escapeHtml(subtitle)}</p>` : ''}
            ${items.length ? `<p class="text-xs text-text-secondary mt-1">Всего записей: ${escapeHtml(String(items.length))}</p>` : ''}
          </div>
        </div>
      </div>
      <div class="p-6 space-y-3">
        ${items.length ? visible.map(renderRow).join('') : `
          <p class="text-sm text-text-secondary">Записи не найдены.</p>
        `}
        ${hiddenCount > 0 || (expanded && items.length > COLLAPSED_COUNT) ? `
          <button
            type="button"
            class="registry-toggle px-4 py-2 rounded-xl text-sm font-medium bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all"
            data-expand-key="${escapeHtml(expandKey)}"
          >
            ${expanded ? 'Свернуть' : `Развернуть ещё ${hiddenCount}`}
          </button>
        ` : ''}
        ${note ? `<p class="text-xs text-text-secondary">${escapeHtml(note)}</p>` : ''}
      </div>
    </div>
  `;
}

export function renderRegistryLoadingHTML(id, title) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6 slide-up" id="${escapeHtml(id)}">
      <div class="flex items-center gap-3">
        <div class="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full shrink-0 motion-safe:transition-transform"></div>
        <div>
          <h2 class="text-sm font-semibold text-text-main">${escapeHtml(title)}</h2>
          <p class="text-xs text-text-secondary mt-0.5">Загружаем данные…</p>
        </div>
      </div>
    </div>
  `;
}

export function renderRegistryErrorHTML(id, title, message) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6 slide-up" id="${escapeHtml(id)}">
      <div class="flex items-start gap-3">
        <i data-lucide="alert-circle" class="w-5 h-5 text-amber-400 shrink-0 mt-0.5"></i>
        <div>
          <h2 class="text-sm font-semibold text-text-main">${escapeHtml(title)}</h2>
          <p class="text-sm text-text-secondary mt-1">${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

export { COLLAPSED_COUNT };
