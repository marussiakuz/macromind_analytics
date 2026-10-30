function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function formatRub(value) {
  if (value == null) return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} млрд ₽`;
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  return `${n.toLocaleString('ru-RU')} ₽`;
}

/**
 * SVG bar chart for a financial series.
 * @param {{year: number, value: number|null}[]} series
 * @param {string} color — bar color
 */
export function renderFinanceChart(series, { color = '#4D966F', title = '' } = {}) {
  const points = (series || []).filter(p => p.value != null);
  if (!points.length) {
    return `<p class="text-sm text-text-secondary">Нет данных для графика.</p>`;
  }
  const w = 520;
  const h = 220;
  const padL = 56;
  const padR = 12;
  const padT = 16;
  const padB = 36;
  const values = points.map(p => Number(p.value));
  const minV = Math.min(...values, 0);
  const maxV = Math.max(...values, 0);
  const range = maxV - minV || 1;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const barW = Math.min(36, plotW / points.length * 0.65);
  const step = plotW / points.length;

  const yFor = (v) => padT + plotH - ((v - minV) / range) * plotH;
  const zeroY = yFor(0);

  const bars = points.map((p, i) => {
    const x = padL + i * step + (step - barW) / 2;
    const v = Number(p.value);
    const y = v >= 0 ? yFor(v) : zeroY;
    const bh = Math.abs(yFor(v) - zeroY);
    return `
      <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(2, bh).toFixed(1)}"
        fill="${v < 0 ? '#C45C5C' : color}" rx="3">
        <title>${escapeHtml(String(p.year))}: ${escapeHtml(formatRub(p.value))}</title>
      </rect>
      <text x="${(x + barW / 2).toFixed(1)}" y="${h - 12}" text-anchor="middle" fill="#8A8A8E" font-size="10">${escapeHtml(String(p.year))}</text>
    `;
  }).join('');

  return `
    <svg viewBox="0 0 ${w} ${h}" class="w-full h-auto" role="img" aria-label="${escapeHtml(title)}">
      <line x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${w - padR}" y2="${zeroY.toFixed(1)}" stroke="#3C3C3C" stroke-width="1" />
      <text x="4" y="${(padT + 10)}" fill="#8A8A8E" font-size="10">${escapeHtml(formatRub(maxV))}</text>
      <text x="4" y="${(padT + plotH)}" fill="#8A8A8E" font-size="10">${escapeHtml(formatRub(minV))}</text>
      ${bars}
    </svg>
  `;
}

/**
 * Блок «Финансовая отчетность» — между карточкой компании и физлицами.
 * @param {object} finances — нормализованный ответ
 */
export function renderFinancesHTML(finances) {
  if (!finances) return '';
  const years = finances.years || [];
  const revenueSeries = years.map(y => ({ year: y.year, value: y.revenue }));
  const profitSeries = years.map(y => ({ year: y.year, value: y.net_profit }));
  const latest = [...years].reverse().find(y => y.revenue != null || y.net_profit != null);
  const reportLinks = finances.report_links || {};
  const linkYears = Object.keys(reportLinks).sort().reverse().slice(0, 5);

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" id="finances-card">
      <div class="p-6 border-b border-card-border">
        <h2 class="text-lg font-semibold text-text-main">Финансовая отчетность</h2>
        <p class="text-sm text-text-secondary mt-1">
          Данные ФНС и Росстата, 2011–2025 · строки 2110 (выручка) и 2400 (чистая прибыль)
        </p>
      </div>

      <div class="p-6 space-y-6">
        ${latest ? `
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div class="bg-surface rounded-xl p-4">
              <div class="text-xs text-text-secondary">Последний год</div>
              <div class="text-lg font-semibold text-text-main mt-1">${escapeHtml(latest.year)}</div>
            </div>
            <div class="bg-surface rounded-xl p-4">
              <div class="text-xs text-text-secondary">Выручка</div>
              <div class="text-lg font-semibold text-text-main mt-1">${escapeHtml(formatRub(latest.revenue))}</div>
            </div>
            <div class="bg-surface rounded-xl p-4">
              <div class="text-xs text-text-secondary">Чистая прибыль</div>
              <div class="text-lg font-semibold ${latest.net_profit != null && Number(latest.net_profit) < 0 ? 'text-red-400' : 'text-text-main'} mt-1">
                ${escapeHtml(formatRub(latest.net_profit))}
              </div>
            </div>
          </div>
        ` : ''}

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-surface rounded-xl p-4">
            <h3 class="text-sm font-semibold text-text-main mb-3">Выручка компании</h3>
            ${renderFinanceChart(revenueSeries, { color: '#4D966F', title: 'Выручка' })}
          </div>
          <div class="bg-surface rounded-xl p-4">
            <h3 class="text-sm font-semibold text-text-main mb-3">Чистая прибыль</h3>
            ${renderFinanceChart(profitSeries, { color: '#68B589', title: 'Чистая прибыль' })}
          </div>
        </div>

        ${years.length ? `
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-text-secondary border-b border-card-border">
                  <th class="py-2 pr-4">Год</th>
                  <th class="py-2 pr-4 text-right">Выручка</th>
                  <th class="py-2 text-right">Чистая прибыль</th>
                </tr>
              </thead>
              <tbody>
                ${[...years].reverse().map(y => `
                  <tr class="border-b border-card-border last:border-b-0">
                    <td class="py-2 pr-4 text-text-main">${escapeHtml(y.year)}</td>
                    <td class="py-2 pr-4 text-right text-text-main">${escapeHtml(formatRub(y.revenue))}</td>
                    <td class="py-2 text-right ${y.net_profit != null && Number(y.net_profit) < 0 ? 'text-red-400' : 'text-text-main'}">
                      ${escapeHtml(formatRub(y.net_profit))}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : ''}

        ${linkYears.length ? `
          <div>
            <h3 class="text-xs text-text-secondary uppercase tracking-wider mb-2">Официальные отчеты (PDF)</h3>
            <div class="flex flex-wrap gap-2">
              ${linkYears.map(year => `
                <a
                  href="${escapeHtml(reportLinks[year])}"
                  target="_blank"
                  rel="noreferrer"
                  class="px-3 py-1.5 rounded-lg text-xs bg-primary/[.18] text-primary hover:bg-primary/[.28] transition-all"
                >
                  ${escapeHtml(year)}
                </a>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

export function renderFinancesErrorHTML(message) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-5 slide-up" id="finances-card">
      <div class="flex items-start gap-3">
        <i data-lucide="alert-circle" class="w-5 h-5 text-amber-400 shrink-0 mt-0.5"></i>
        <div>
          <h3 class="text-sm font-semibold text-text-main">Финансовая отчетность</h3>
          <p class="text-sm text-text-secondary mt-1">${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

export function renderFinancesLoadingHTML() {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-5 slide-up" id="finances-card">
      <div class="flex items-center gap-3">
        <div class="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
        <p class="text-sm text-text-secondary">Загружаем финансовую отчетность…</p>
      </div>
    </div>
  `;
}
