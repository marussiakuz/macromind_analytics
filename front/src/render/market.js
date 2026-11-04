import { marketState } from '../market/state.js';
import { getDirections, hasEvidenceReport, hasCompanyDirections } from '../market/report-shape.js';
import { renderEvidenceSourcesHTML, renderKnowledgeSearchResultsHTML } from './knowledge.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

const ROLE_LABELS = {
  manufacturer: 'Производитель',
  distributor: 'Дистрибьютор / перепродажа',
  integrator: 'Интегратор / сборка',
  service_provider: 'Сервисные услуги',
  unknown: 'Роль не определена',
};

const RELATION_LABELS = {
  direct_competitor: { text: 'Прямой конкурент', cls: 'bg-red-900/[.30] text-red-400' },
  product_analog: { text: 'Продуктовый аналог', cls: 'bg-amber-900/[.30] text-amber-400' },
  supplier_partner: { text: 'Поставщик / партнёр', cls: 'bg-green-900/[.30] text-green-400' },
  candidate_for_check: { text: 'Кандидат для проверки', cls: 'bg-[#383838] text-text-secondary' },
  rejected: { text: 'Отклонён', cls: 'bg-[#383838] text-text-secondary' },
};

function directionLabel(directions, id) {
  const d = (directions || []).find(x => x.direction_id === id);
  return d?.product_category_ru || d?.product_category_en || id || '';
}

function renderDirectionBlock(report) {
  const directions = report?.company?.directions || [];
  if (!directions.length) {
    return `<section class="bg-surface rounded-xl p-4">
      <h3 class="font-semibold text-text-main mb-3">Что делает компания</h3>
      <p class="text-sm text-text-secondary">Направления не подтверждены источниками. Общие слова ОКВЭД не используются как доказательство.</p>
    </section>`;
  }
  const siteStatus = report?.company?.site_status;
  const normalize = text => String(text || '').replace(/\s+/g, ' ').trim();
  const keyOf = e => `${e.url || ''}|${normalize(e.quote)}`;
  const usage = new Map();
  directions.forEach(d => [...new Set((d.evidence || []).map(keyOf))].forEach(k => usage.set(k, (usage.get(k) || 0) + 1)));
  const uniqueEvidence = rows => {
    const output = [];
    for (const e of rows || []) {
      const text = normalize(e.quote);
      if (!text) continue;
      if (output.some(q => q.url === e.url && (normalize(q.quote).includes(text) || text.includes(normalize(q.quote))))) continue;
      output.push(e);
    }
    return output;
  };
  const evidenceHTML = rows => uniqueEvidence(rows).map(e => `<blockquote class="border-l-2 border-primary pl-3 my-2 text-xs">${escapeHtml(e.quote || '')}
    ${e.url ? `<div class="mt-1 break-words">${sourceLink(e, e.title || 'Открыть источник')}</div>` : ''}</blockquote>`).join('');
  const sharedEvidence = uniqueEvidence(directions.flatMap(d => (d.evidence || []).filter(e => usage.get(keyOf(e)) > 1)));
  const rows = directions.map(d => {
    const ownEvidence = (d.evidence || []).filter(e => usage.get(keyOf(e)) === 1);
    const quotes = ownEvidence.length ? `<details class="mt-2"><summary class="text-xs text-text-secondary cursor-pointer">Основания этого направления</summary>${evidenceHTML(ownEvidence)}</details>` : '';
    const brands = (d.brands || []).map(b => {
      const rel = { own_brand: 'свой бренд', supplier: 'поставщик', resale: 'перепродажа', unknown: 'неизвестно' }[b.relation] || b.relation;
      return `${escapeHtml(b.name)} <span class="text-text-secondary">(${escapeHtml(rel)})</span>`;
    }).join(', ');
    const lim = (d.limitations || []).map(l => `<div class="text-xs text-amber-400">${escapeHtml(l)}</div>`).join('');
    return `<div class="border-t border-card-border py-3 first:border-t-0">
      <div class="flex flex-wrap items-center gap-2">
        <strong class="text-sm">${escapeHtml(d.product_category_ru || d.product_category_en || d.direction_id)}</strong>
        <span class="text-xs px-2 py-0.5 rounded bg-[#383838] text-text-secondary">${escapeHtml(ROLE_LABELS[d.role] || d.role)}</span>
        <span class="text-xs px-2 py-0.5 rounded bg-[#383838] text-text-secondary">${escapeHtml(({supported:'Есть подтверждения',hypothesis:'Предположение',unresolved:'Требует уточнения'})[d.status] || d.status || '')}</span>
        <span class="text-xs text-text-secondary">${escapeHtml(d.geography || 'geo unknown')}</span>
      </div>
      ${d.description ? `<p class="text-sm mt-2 leading-relaxed">${escapeHtml(d.description)}</p>` : ''}
      ${d.product_category_en && d.product_category_en !== d.product_category_ru ? `<div class="text-xs text-text-secondary mt-1">${escapeHtml(d.product_category_en)}</div>` : ''}
      ${d.applications?.length ? `<div class="text-xs text-text-secondary mt-1">Применение: ${escapeHtml(d.applications.join(' · '))}</div>` : ''}
      ${d.buyer_segments?.length ? `<div class="text-xs text-text-secondary">Покупатели: ${escapeHtml(d.buyer_segments.join(' · '))}</div>` : ''}
      ${brands ? `<div class="text-xs text-text-secondary mt-1">Бренды: ${brands}</div>` : ''}
      ${quotes}
      ${lim ? `<details class="mt-2"><summary class="text-xs text-amber-400 cursor-pointer">Что не удалось подтвердить</summary>${lim}</details>` : ''}
    </div>`;
  }).join('');
  return `<section class="bg-surface rounded-xl p-4">
    <h3 class="font-semibold text-text-main mb-1">Что делает компания</h3>
    <p class="text-xs text-text-secondary mb-3">Направления и роли с источниками${siteStatus ? ` · сайт: ${escapeHtml(siteStatus)}` : ''}</p>
    ${rows}
    ${sharedEvidence.length ? `<details class="mt-3 border-t border-card-border pt-3"><summary class="text-xs text-text-secondary cursor-pointer">Общие источники направлений — показаны один раз</summary>${evidenceHTML(sharedEvidence)}</details>` : ''}
  </section>`;
}

function renderCompetitorTable(rows, directions, title, sources = new Map()) {
  if (!rows?.length) {
    return `<section class="bg-surface rounded-xl p-4"><h3 class="font-semibold text-text-main mb-3">${title}</h3>
      <p class="text-sm text-text-secondary">Сопоставимые продукты пока не подтверждены источниками.</p></section>`;
  }
  return `<section class="bg-surface rounded-xl p-4">
    <h3 class="font-semibold text-text-main mb-3">${title} · ${rows.length}</h3>
    <div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="text-left text-text-secondary">
      <th class="p-2">Компания</th><th class="p-2">Продукция / услуги</th><th class="p-2">Сходство и источники</th>
    </tr></thead><tbody>
    ${rows.map(r => {
      const rel = RELATION_LABELS[r.relation_class] || RELATION_LABELS.product_analog;
      const citations = (r.quotes || []).map(q => ({...q, url:q.url || sources.get(q.evidence_id)?.url, title:q.title || sources.get(q.evidence_id)?.title}));
      const links = [...new Set([...(r.links || []), ...(r.evidence_ids || []).map(id => sources.get(id)?.url), ...citations.map(q => q.url)].filter(Boolean))];
      return `<tr class="border-t border-card-border">
        <td class="p-2 align-top"><strong>${escapeHtml(r.name)}</strong>
          <div class="text-xs text-text-secondary">${escapeHtml(r.country || r.territory_status || '')}</div></td>
        <td class="p-2 align-top">
          <p>${escapeHtml(r.specialization || 'Описание не подтверждено')}</p>
          ${r.direction_id ? `<div class="text-xs text-text-secondary mt-1">${escapeHtml(directionLabel(directions, r.direction_id))}</div>` : ''}
          <span class="text-xs px-2 py-0.5 rounded ${rel.cls}">${escapeHtml(rel.text)}</span>
        </td>
        <td class="p-2"><p>${escapeHtml(r.why_competes && r.why_competes !== r.specialization ? r.why_competes : 'Основание сравнения требует уточнения')}</p>
          ${links.slice(0, 4).map((u, i) => `<div class="text-xs mt-1 break-words">${sourceLink({url:u}, `Источник ${i + 1}`)}</div>`).join('')}
          ${refsFromQuotes({...r, quotes:citations})}
        </td>
      </tr>`;
    }).join('')}
    </tbody></table></div>
  </section>`;
}

function refsFromQuotes(item) {
  if (!item?.quotes?.length) return '';
  return `<details class="text-xs text-text-secondary mt-2"><summary class="cursor-pointer">Подтверждающие фрагменты</summary>${item.quotes.map(q => `<blockquote class="border-l-2 border-primary pl-3 my-2">${escapeHtml(q.quote || '')}${q.url ? `<div class="mt-1">${sourceLink(q, q.url)}</div>` : ''}</blockquote>`).join('')}</details>`;
}

function renderSuppliersBlock(comps, directions) {
  const rows = comps?.suppliers_partners || [];
  if (!rows.length) return '';
  return `<section class="bg-surface rounded-xl p-4">
    <h3 class="font-semibold text-text-main mb-2">Поставщики и партнёры</h3>
    <p class="text-xs text-text-secondary mb-2">Отдельно от конкурентов: поставщик по одному направлению не является прямым конкурентом по всему бизнесу.</p>
    <ul class="text-sm space-y-2">
      ${rows.map(r => `<li>
        <strong>${escapeHtml(r.name)}</strong>
        <span class="text-xs text-text-secondary ml-2">${escapeHtml(directionLabel(directions, r.direction_id))}</span>
        <div class="text-xs text-text-secondary">${escapeHtml(r.specialization || r.why_competes || '')}</div>
      </li>`).join('')}
    </ul>
  </section>`;
}

function money(value, currency = 'RUB') {
  if (value == null || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)} млрд ${currency}`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)} млн ${currency}`;
  return `${n.toLocaleString('ru-RU')} ${currency}`;
}

const TRIAG_LABELS = {
  close: { text: 'Расхождение ≤ 20%', cls: 'bg-green-900/[.30] text-green-400' },
  review_required: { text: 'Расхождение 20–30%', cls: 'bg-amber-900/[.30] text-amber-400' },
  divergent: { text: 'Расхождение > 30%', cls: 'bg-red-900/[.30] text-red-400' },
  both_zero: { text: 'Обе оценки нулевые', cls: 'bg-[#383838] text-text-secondary' },
  not_comparable: { text: 'Оценки несопоставимы', cls: 'bg-red-900/[.30] text-red-400' },
  insufficient_data: { text: 'Недостаточно данных', cls: 'bg-amber-900/[.30] text-amber-400' },
  shared_evidence: { text: 'Общий первоисточник', cls: 'bg-amber-900/[.30] text-amber-400' },
};

function sourceLink(source, label) {
  const url = source?.url || '';
  if (!/^https?:\/\//i.test(url)) return escapeHtml(label || source?.title || 'Источник');
  return `<a class="text-primary underline" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label || source?.title || 'Источник')}</a>`;
}

function renderEvidenceReport(report) {
  const sources = new Map((report.sources || []).map(s => [s.id, s]));
  const refs = (item) => `<div class="text-xs mt-2 space-y-1">${(item.evidence_ids || []).map(id =>
    `<span class="mr-3">${sourceLink(sources.get(id), sources.get(id)?.title || id)}</span>`).join('')}</div>
    ${(item.quotes || []).length ? `<details class="text-xs text-text-secondary mt-2"><summary class="cursor-pointer">Подтверждающие фрагменты</summary>${item.quotes.map(q => `<blockquote class="border-l-2 border-primary pl-3 my-2">${escapeHtml(q.quote)}</blockquote>`).join('')}</details>` : ''}`;
  const labels = {world: 'Мировой рынок', russia: 'Российский рынок', trends: 'Технологические тренды', market_risks: 'Рыночные риски', technology_risks: 'Технологические риски'};
  const sections = Object.entries(labels).map(([key, label]) => `<section class="bg-surface rounded-xl p-4">
    <h3 class="font-semibold text-text-main mb-3">${label}</h3>
    ${(report.sections?.[key] || []).length ? report.sections[key].map(p => `<div class="mb-4"><p class="text-sm text-text-main leading-relaxed whitespace-pre-line">${escapeHtml(p.text)}</p>${refs(p)}</div>`).join('')
      : '<p class="text-sm text-text-secondary">В найденных источниках недостаточно сведений для этого раздела.</p>'}</section>`).join('');
  const directions = report.company?.directions || [];
  const comps = report.competitors || {};
  const tables = renderCompetitorTable(comps.russia, directions, 'Конкуренты в России', sources)
    + renderCompetitorTable(comps.world, directions, 'Зарубежные аналоги', sources);
  return `<div class="space-y-4">
    ${renderDirectionBlock(report)}
    <section class="bg-surface rounded-xl p-4"><h3 class="font-semibold mb-2">Продукт и покупатели</h3><p class="text-sm leading-relaxed">${escapeHtml(report.company?.about || '')}</p><p class="text-sm text-text-secondary mt-2">Продукт: ${escapeHtml(report.company?.product || 'Требует уточнения')}</p><p class="text-sm text-text-secondary">Покупатели: ${escapeHtml(report.company?.buyer || 'Требуют уточнения')}</p></section>
    ${sections}${tables}
    ${renderSuppliersBlock(comps, directions)}
    ${(report.questions || []).length ? `<section class="bg-surface rounded-xl p-4"><h3 class="font-semibold mb-2">Что уточнить у компании</h3><ul class="list-disc ml-5 text-sm">${report.questions.map(q => `<li>${escapeHtml(q)}</li>`).join('')}</ul></section>` : ''}
    ${(report.gaps || []).length ? `<section class="bg-surface rounded-xl p-4"><h3 class="font-semibold mb-2">Недостающие данные</h3><ul class="list-disc ml-5 text-xs text-text-secondary">${report.gaps.map(q => `<li>${escapeHtml(q)}</li>`).join('')}</ul></section>` : ''}
    <p class="text-xs text-text-secondary">${escapeHtml((report.limitations || []).join(' '))}</p>
  </div>`;
}

/**
 * Аналитический отчет в стиле эталонного PDF (рынок + конкуренты, без судов).
 */
export function renderAnalyticalReportHTML(report) {
  if (!report) return '';
  if (report.sections) return renderEvidenceReport(report);
  const c = report.company || {};
  const m = report.market || {};
  const comps = report.competitors || {};
  return `
    <div class="space-y-5">
      <div class="bg-surface rounded-xl p-4">
        <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Раздел 1. Компания</h3>
        <p class="text-sm text-text-main">${escapeHtml(c.about || '')}</p>
        <ul class="text-sm text-text-secondary mt-2 space-y-1">
          <li>Наименование: ${escapeHtml(c.name || '—')}</li>
          <li>ИНН: ${escapeHtml(c.inn || '—')}</li>
          ${c.site ? `<li>Сайт: ${escapeHtml(c.site)}</li>` : ''}
          <li>Продукция: ${escapeHtml(c.product || '—')}</li>
          <li>Покупатели: ${escapeHtml(c.buyer || '—')}</li>
        </ul>
      </div>

      <div class="bg-surface rounded-xl p-4">
        <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Финансовые показатели</h3>
        ${(report.finances || []).length ? `
          <table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-text-secondary">
              <th class="py-1">Год</th><th>Выручка</th><th>Чистая прибыль</th>
            </tr></thead>
            <tbody>
              ${(report.finances || []).map(row => `
                <tr class="border-t border-card-border">
                  <td class="py-1">${escapeHtml(String(row.year ?? '—'))}</td>
                  <td>${escapeHtml(money(row.revenue))}</td>
                  <td>${escapeHtml(money(row.net_profit))}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        ` : '<p class="text-sm text-text-secondary">Финансовая отчетность не получена.</p>'}
      </div>

      <div class="bg-surface rounded-xl p-4">
        <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Мировой и российский рынки</h3>
        <p class="text-sm text-text-secondary mb-2"><b>Мировой.</b> ${escapeHtml(m.world || '')}</p>
        <p class="text-sm text-text-secondary mb-2"><b>Россия.</b> ${escapeHtml(m.russia || '')}</p>
        ${(m.trends || []).length ? `
          <p class="text-xs uppercase text-text-secondary mt-3 mb-1">Тренды</p>
          <ul class="text-sm text-text-secondary list-disc ml-5 space-y-1">
            ${m.trends.slice(0, 6).map(t => `<li>${escapeHtml(t)}</li>`).join('')}
          </ul>
        ` : ''}
        ${(m.risks || []).length ? `
          <p class="text-xs uppercase text-text-secondary mt-3 mb-1">Риски</p>
          <ul class="text-sm text-text-secondary list-disc ml-5 space-y-1">
            ${m.risks.slice(0, 6).map(t => `<li>${escapeHtml(t)}</li>`).join('')}
          </ul>
        ` : ''}
        ${(m.fragments || []).length ? `
          <p class="text-xs uppercase text-text-secondary mt-3 mb-1">Числа из источников</p>
          <ul class="text-xs text-text-secondary space-y-1">
            ${m.fragments.slice(0, 6).map(f => `
              <li>${escapeHtml(f.snippet || '')} <span class="text-text-secondary/70">(${escapeHtml(f.source || f.title || '')})</span></li>
            `).join('')}
          </ul>
        ` : ''}
      </div>

      <div class="bg-surface rounded-xl p-4">
        <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Конкурентный анализ</h3>
        <p class="text-xs text-text-secondary mb-2">Аналоги в мире</p>
        ${(comps.world || []).length ? `
          <table class="w-full text-sm mb-3">
            <thead><tr class="text-left text-xs text-text-secondary"><th class="py-1">Компания</th><th>Специализация</th></tr></thead>
            <tbody>${comps.world.map(r => `
              <tr class="border-t border-card-border">
                <td class="py-1">${escapeHtml(r.name)}</td>
                <td class="text-text-secondary">${escapeHtml(r.specialization || '—')}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        ` : '<p class="text-sm text-text-secondary mb-3">Не выявлены.</p>'}
        <p class="text-xs text-text-secondary mb-2">Конкуренты в России</p>
        ${(comps.russia || []).length ? `
          <table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-text-secondary"><th class="py-1">Компания</th><th>Специализация</th></tr></thead>
            <tbody>${comps.russia.map(r => `
              <tr class="border-t border-card-border">
                <td class="py-1">${escapeHtml(r.name)}</td>
                <td class="text-text-secondary">${escapeHtml(r.specialization || '—')}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        ` : '<p class="text-sm text-text-secondary">Не подтверждены.</p>'}
        ${comps.suppliers_partners?.length ? `
          <p class="text-xs text-text-secondary mt-4 mb-1">Поставщики и партнёры (не конкуренты)</p>
          <ul class="text-xs text-text-secondary list-disc ml-5">${comps.suppliers_partners.map(s => `<li>${escapeHtml(s.name)} — ${escapeHtml(s.specialization || '')}</li>`).join('')}</ul>
        ` : ''}
        ${comps.note ? `<p class="text-xs text-text-secondary mt-2">${escapeHtml(comps.note)}</p>` : ''}
      </div>
    </div>
  `;
}

/**
 * Компактный блок «Анализ рынка и конкурентов» (plan §4.1).
 * Ставится сразу после finances-area, перед timeline-area.
 */
export function renderMarketSummaryHTML(summary, { companyName, inn } = {}) {
  if (marketState.loading) return `<div id="market-area" class="bg-card rounded-2xl p-6"><h2 class="text-lg font-semibold">Анализ рынка и конкурентов</h2><p id="market-progress" class="text-sm text-text-secondary mt-2">${escapeHtml(marketState.progress || 'Проверяем доступность модели…')}</p></div>`;
  if (marketState.error) return `<div id="market-area" class="bg-card rounded-2xl p-6"><h2 class="text-lg font-semibold">Анализ рынка и конкурентов</h2><p class="text-sm mt-2">${escapeHtml(marketState.error)}</p><button id="market-refresh-analysis" class="mt-3 px-3 py-2 bg-primary rounded-xl">Повторить исследование</button></div>`;
  if (!summary) return '';

  const scope = summary?.market_scope || {};
  const td = summary?.estimates_rf;
  const tri = TRIAG_LABELS[summary?.triangulation_status] || TRIAG_LABELS.insufficient_data;
  const complete = summary?.data_completeness || {};
  const report = summary?.analytical_report;
  if (hasEvidenceReport(summary)) {
    const count = (report.sources || []).length;
    const hasContent = Object.values(report.sections || {}).some(rows => rows?.length);
    return `<div class="bg-card text-text-main rounded-2xl shadow-soft overflow-hidden slide-up" id="market-area">
      <div class="p-6 border-b border-card-border flex flex-wrap justify-between gap-3">
        <div><h2 class="text-lg font-semibold">Анализ рынка и конкурентов</h2><p class="text-sm text-text-secondary mt-1">${escapeHtml(companyName || report.company?.name || '')} · ${escapeHtml(inn || report.company?.inn || '')}</p><p class="text-xs text-text-secondary">Источников: ${count} · ${escapeHtml(summary.as_of || '')}</p></div>
        <div class="flex items-center gap-2"><span class="text-xs text-text-secondary">${hasContent ? 'Обзор подготовлен · проверьте источники' : 'Исследование не завершено'}</span>
        <button id="market-refresh-analysis" class="px-3 py-2 bg-primary text-white rounded-xl text-sm">Обновить исследование</button>
        <button id="market-download-report" class="px-3 py-2 border border-card-border rounded-xl text-sm">Скачать отчёт</button></div>
      </div><div class="p-6 space-y-4">${!hasContent ? `<p class="text-sm text-text-secondary">${escapeHtml((summary.limitations || []).join(' ') || 'Не удалось получить подтверждённые выводы. Обновите исследование.')}</p>` : ''}${renderAnalyticalReportHTML(report)}
      <details class="text-xs text-text-secondary"><summary>Состояние источников</summary>${(summary.external_source_states || []).map(s => `<div>${escapeHtml(s.source)}: ${escapeHtml(s.status)} · ${escapeHtml(s.message || '')}</div>`).join('')}${(summary.errors || []).map(e => `<div>${escapeHtml(e.error)}</div>`).join('')}</details>
      </div></div>`;
  }


  if (summary.auto) {
    return `<div id="market-area" class="bg-card text-text-main rounded-2xl p-6">
      <h2 class="text-lg font-semibold">Анализ рынка и конкурентов</h2>
      <p class="text-sm text-text-secondary mt-2">Сохранён старый формат анализа. Обновите исследование, чтобы получить обзор рынка, конкурентов и ссылки на источники.</p>
      <button id="market-refresh-analysis" class="mt-3 px-3 py-2 bg-primary text-white rounded-xl">Обновить исследование</button>
    </div>`;
  }

  return `
    <div class="bg-card text-text-main rounded-2xl shadow-soft overflow-hidden slide-up" id="market-area">
      <div class="p-6 border-b border-card-border flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-text-main">Анализ рынка и конкурентов</h2>
          <p class="text-sm text-text-secondary mt-1">
            ${escapeHtml(scope.product || 'Границы рынка не заданы')}
            ${scope.reference_period ? ` · период ${escapeHtml(scope.reference_period)}` : ''}
            ${summary?.as_of ? ` · данные на ${escapeHtml(summary.as_of)}` : ''}
          </p>
          ${companyName ? `<p class="text-xs text-text-secondary mt-1">Компания: ${escapeHtml(companyName)}${inn ? ` (ИНН ${escapeHtml(inn)})` : ''}</p>` : ''}
        </div>
        <div class="flex items-center gap-2">
          <span class="px-3 py-1.5 rounded-xl text-xs font-medium ${tri.cls}">${escapeHtml(tri.text)}</span>
          <button type="button" id="market-open-detail"
            class="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm rounded-xl font-medium transition-all">
            Открыть исследование
          </button>
        </div>
      </div>

      <div class="p-6 space-y-5">
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div class="bg-surface rounded-xl p-4">
            <div class="text-xs text-text-secondary">Оценка сверху вниз (РФ)</div>
            <div class="text-lg font-semibold text-text-main mt-1">
              ${td?.value != null ? escapeHtml(money(td.value, td.currency)) : '—'}
            </div>
            <div class="text-xs text-text-secondary mt-1">${td?.formula ? escapeHtml(td.formula) : 'не рассчитано'}</div>
          </div>
          <div class="bg-surface rounded-xl p-4">
            <div class="text-xs text-text-secondary">Оценка снизу вверх</div>
            <div class="text-lg font-semibold text-text-main mt-1">
              ${summary?.estimates_world?.value != null
                ? escapeHtml(money(summary.estimates_world.value))
                : complete.has_bottom_up ? 'см. исследование' : '—'}
            </div>
            <div class="text-xs text-text-secondary mt-1">${complete.has_bottom_up ? 'потенциал / спрос' : 'не рассчитано'}</div>
          </div>
          <div class="bg-surface rounded-xl p-4">
            <div class="text-xs text-text-secondary">Полнота данных</div>
            <div class="text-sm text-text-main mt-2 space-y-1">
              <div>${complete.has_top_down ? '✓' : '—'} верхняя оценка</div>
              <div>${complete.has_bottom_up ? '✓' : '—'} нижняя оценка</div>
              <div>${complete.has_triangulation ? '✓' : '—'} сопоставление методов</div>
              ${complete.has_registry_evidence ? '<div>✓ данные реестров</div>' : ''}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Границы рынка</h3>
            <ul class="text-sm text-text-secondary space-y-1">
              <li>Продукт: ${escapeHtml(scope.product || '—')}</li>
              <li>Покупатель: ${escapeHtml(scope.buyer || '—')}</li>
              <li>Показатель: ${escapeHtml(scope.measure_type || 'revenue')}</li>
              <li>Страны: ${escapeHtml((scope.countries || []).join(', ') || '—')}</li>
              ${scope.okved ? `<li>ОКВЭД: ${escapeHtml(scope.okved)}</li>` : ''}
              ${(scope.exclude || []).length ? `<li>Исключения: ${escapeHtml(scope.exclude.join('; '))}</li>` : ''}
            </ul>
            ${(summary?.market_estimates_from_snippets || []).length ? `
              <h3 class="text-xs uppercase tracking-wider text-text-secondary mt-4 mb-2">Оценки из источников</h3>
              <ul class="text-xs text-text-secondary space-y-1">
                ${(summary.market_estimates_from_snippets || []).slice(0, 5).map(e => `
                  <li>${escapeHtml(String(e.value ?? e.value_raw ?? ''))} ${escapeHtml(e.unit || '')} — ${escapeHtml(e.source || e.title || '')}</li>
                `).join('')}
              </ul>
            ` : ''}
          </div>
          <div>
            <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Конкуренты</h3>
            <p class="text-sm text-text-secondary">
              ${(report?.competitors?.world?.length || report?.competitors?.russia?.length)
                ? `Мировые: ${report.competitors.world?.length || 0} · РФ: ${report.competitors.russia?.length || 0}`
                : 'Не выявлены в доступных источниках (без судебных сторон).'}
            </p>
            <h3 class="text-xs uppercase tracking-wider text-text-secondary mt-4 mb-2">Ограничения</h3>
            <p class="text-sm text-text-secondary">
              ${(summary?.limitations || []).length
                ? escapeHtml(summary.limitations.slice(0, 4).join('; '))
                : 'Оценка не является инвестиционной рекомендацией.'}
            </p>
            ${(summary?.external_source_states || []).length ? `
              <h3 class="text-xs uppercase tracking-wider text-text-secondary mt-4 mb-2">Внешние источники</h3>
              <ul class="text-xs text-text-secondary space-y-1">
                ${summary.external_source_states.map(s => `
                  <li>
                    <span class="text-text-main">${escapeHtml(s.source)}</span>
                    · ${escapeHtml(s.status)} · записей: ${escapeHtml(String(s.count ?? 0))}
                    ${s.message ? ` · ${escapeHtml(s.message)}` : ''}
                  </li>
                `).join('')}
              </ul>
            ` : ''}
            <div class="mt-4">
              ${renderEvidenceSourcesHTML(
                summary?.evidence_refs || summary?.external_evidence || [],
                {
                  title: 'Источники выводов',
                  emptyText: 'Внешние источники ещё не подключены.',
                },
              )}
            </div>
          </div>
        </div>

        ${report ? `
          <div class="mt-2">
            <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Аналитический отчет</h3>
            ${renderAnalyticalReportHTML(report)}
          </div>
        ` : ''}
        ${(summary?.llm_interpretation || []).length ? `
          <div class="bg-surface rounded-xl p-4">
            <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Интерпретация (не факт)</h3>
            <ul class="text-sm text-text-secondary space-y-1">
              ${summary.llm_interpretation.slice(0, 5).map(c => `
                <li class="flex flex-wrap items-start gap-2">
                  <span class="px-2 py-0.5 rounded-lg text-xs bg-amber-900/[.30] text-amber-400 shrink-0">интерпретация</span>
                  <span>${escapeHtml(c.text || c.statement || '')}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}

        <div class="flex flex-wrap gap-2">
          <button type="button" id="market-open-detail"
            class="px-4 py-2 rounded-xl text-sm bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all">
            Подробности
          </button>
          <button type="button" id="market-link-deal"
            class="px-4 py-2 rounded-xl text-sm bg-surface border border-card-border text-text-secondary hover:text-text-main transition-all">
            Связать с заявкой
          </button>
          <button type="button" id="market-download-report"
            class="px-4 py-2 rounded-xl text-sm bg-primary text-white hover:bg-primary-hover transition-all">
            Скачать отчет
          </button>
        </div>
      </div>

      ${renderLLMInterpretationHTML(summary)}

      ${marketState.detailOpen ? renderMarketDetailHTML() : ''}
    </div>
  `;
}

/** Интерпретация Qwen — после финансовых показателей / в блоке рынка. */
function renderLLMInterpretationHTML(summary) {
  const claims = summary?.llm_interpretation || [];
  const status = summary?.llm_status;
  if (status && status !== 'ok') {
    return `
      <div class="px-6 pb-6">
        <div class="bg-surface rounded-xl p-4 border border-card-border">
          <h3 class="text-sm font-semibold text-text-main">Интерпретация модели</h3>
          <p class="text-xs text-text-secondary mt-1">
            ${escapeHtml(summary?.llm_error || 'Интерпретация недоступна. Факты реестров показаны выше.')}
          </p>
        </div>
      </div>
    `;
  }
  if (!claims.length && !summary?.llm_summary) return '';
  return `
    <div class="px-6 pb-6 space-y-3">
      <div class="bg-surface rounded-xl p-4">
        <h3 class="text-sm font-semibold text-text-main">Интерпретация модели</h3>
        <p class="text-xs text-text-secondary mt-1">
          ${escapeHtml(summary.llm_model || '')} · выводы требуют проверки аналитиком
        </p>
        ${summary.llm_summary ? `<p class="text-sm text-text-main mt-2">${escapeHtml(summary.llm_summary)}</p>` : ''}
      </div>
      ${claims.length ? `
        <div class="space-y-2">
          ${claims.map(c => `
            <div class="bg-surface rounded-xl p-3 border border-card-border">
              <div class="flex flex-wrap gap-2 text-xs text-text-secondary">
                <span class="px-2 py-0.5 rounded bg-primary/[.18] text-primary">${escapeHtml(c.claim_type)}</span>
                <span class="px-2 py-0.5 rounded bg-amber-900/[.30] text-amber-400">${escapeHtml(c.verification_status)}</span>
              </div>
              <p class="text-sm text-text-main mt-2">${escapeHtml(c.statement)}</p>
              ${(c.limitations || []).length ? `
                <p class="text-xs text-text-secondary mt-1">Ограничения: ${escapeHtml(c.limitations.join('; '))}</p>
              ` : ''}
            </div>
          `).join('')}
        </div>
      ` : ''}
      ${(summary.llm_risks || []).length ? `
        <div class="text-xs text-text-secondary">Риски: ${escapeHtml(summary.llm_risks.join('; '))}</div>
      ` : ''}
      ${(summary.llm_questions || []).length ? `
        <div class="text-xs text-text-secondary">Вопросы: ${escapeHtml(summary.llm_questions.join('; '))}</div>
      ` : ''}
    </div>
  `;
}

/** Подробный экран: факты автоанализа без кнопок расчёта. */
export function renderMarketDetailHTML() {
  const s = marketState;
  const summary = s.summary || {};
  const complete = summary.data_completeness || {};
  const sections = complete.registry_sections || {};
  return `
    <div class="border-t border-card-border p-6 space-y-5" id="market-detail">
      <div class="flex items-center justify-between">
        <h3 class="text-base font-semibold text-text-main">Источники и полнота (автоанализ)</h3>
        <button type="button" id="market-close-detail"
          class="text-sm text-text-secondary hover:text-text-main">Свернуть</button>
      </div>

      ${s.loading ? `
        <div class="flex items-center gap-3">
          <div class="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full"></div>
          <p class="text-sm text-text-secondary">Обновляем данные анализа…</p>
        </div>
      ` : ''}

      ${s.error ? `
        <div class="bg-surface rounded-xl p-4 border border-red-800/40 text-sm text-red-400">${escapeHtml(s.error)}</div>
      ` : ''}

      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        ${Object.entries(sections).map(([k, v]) => `
          <div class="bg-surface rounded-xl px-3 py-2">
            <div class="text-xs text-text-secondary">${escapeHtml(k)}</div>
            <div class="text-sm text-text-main">${escapeHtml(String(v))}</div>
          </div>
        `).join('')}
      </div>

      ${(complete.last_revenue) ? `
        <div class="bg-surface rounded-xl p-4">
          <h4 class="text-sm font-semibold text-text-main mb-1">Финансы</h4>
          <p class="text-sm text-text-secondary">
            ${escapeHtml(String(complete.last_revenue.year ?? ''))} ·
            выручка ${escapeHtml(String(complete.last_revenue.revenue ?? '—'))} ·
            прибыль ${escapeHtml(String(complete.last_revenue.net_profit ?? '—'))}
          </p>
        </div>
      ` : ''}

      <div>
        <h4 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Наблюдения реестров</h4>
        <ul class="text-sm text-text-secondary space-y-1">
          ${(summary.evidence_refs || []).map(e => `
            <li>${escapeHtml(String(e.name))}: ${escapeHtml(String(e.count))}</li>
          `).join('') || '<li>Нет наблюдений.</li>'}
        </ul>
      </div>

      <div>
        <h4 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Кандидаты в конкуренты</h4>
        <p class="text-sm text-text-secondary">
          ${(summary.competitor_findings || []).join('; ') || 'Не выявлены по реестрам.'}
        </p>
      </div>

      <div>
        <h4 class="text-xs uppercase tracking-wider text-text-secondary mb-2">Поиск доказательств</h4>
        <p class="text-xs text-text-secondary mb-2">
          Поиск по разрешённому корпусу. Отсутствие доказательств — нормальный результат.
        </p>
        <form id="market-knowledge-search-form" class="flex flex-col sm:flex-row gap-2 mb-3">
          <input
            type="text"
            id="market-knowledge-query"
            value="${escapeHtml(marketState.knowledgeQuery || '')}"
            placeholder="например: поставщики RPA в РФ"
            class="input-field flex-1 px-3 py-2 rounded-xl text-sm focus:outline-none transition-all"
          />
          <button
            type="submit"
            class="px-4 py-2 rounded-xl text-sm bg-primary text-white hover:bg-primary-hover transition-all whitespace-nowrap"
          >
            Найти
          </button>
        </form>
        ${marketState.knowledgeError
          ? `<p class="text-sm text-red-400 mb-2">${escapeHtml(marketState.knowledgeError)}</p>`
          : ''}
        ${marketState.knowledgeLoading
          ? `<div class="flex items-center gap-2 text-sm text-text-secondary">
               <span class="inline-block w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></span>
               Поиск по базе знаний…
             </div>`
          : marketState.knowledgeResult
            ? renderKnowledgeSearchResultsHTML(marketState.knowledgeResult)
            : ''}
      </div>
    </div>
  `;
}

function renderMDSResultHTML(mds) {
  const coords = mds.coordinates || [];
  const w = 280;
  const h = 200;
  const pad = 28;
  const xs = coords.map(c => c.x);
  const ys = coords.map(c => c.y);
  const minX = Math.min(...xs, 0);
  const maxX = Math.max(...xs, 0);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, 0);
  const sx = v => pad + ((v - minX) / (maxX - minX || 1)) * (w - 2 * pad);
  const sy = v => h - pad - ((v - minY) / (maxY - minY || 1)) * (h - 2 * pad);
  return `
    <div class="pt-2 space-y-2">
      <div class="text-xs text-text-secondary">
        Статус: ${escapeHtml(mds.status)} · ${escapeHtml(mds.message || '')}
        ${mds.relative_distance_error != null ? ` · ошибка восстановления ${(Number(mds.relative_distance_error) * 100).toFixed(2)}%` : ''}
      </div>
      ${mds.status === 'ok' || mds.status === 'degenerate' ? `
        <svg viewBox="0 0 ${w} ${h}" class="w-full max-w-sm h-auto bg-card rounded-lg">
          <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#3C3C3C" />
          <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="#3C3C3C" />
          ${coords.map(c => `
            <circle cx="${sx(c.x).toFixed(1)}" cy="${sy(c.y).toFixed(1)}" r="5" fill="#4D966F" />
            <text x="${(sx(c.x) + 8).toFixed(1)}" y="${(sy(c.y) + 4).toFixed(1)}" fill="#8A8A8E" font-size="10">${escapeHtml(c.id)}</text>
          `).join('')}
        </svg>
        <div class="text-xs text-text-secondary">Оси: ${escapeHtml((mds.axes || []).join(' / '))} — интерпретация отдельно с основаниями.</div>
      ` : `<div class="text-xs text-text-secondary">${escapeHtml(mds.message || 'Карта недоступна')}</div>`}
    </div>
  `;
}

function renderDelphiSummaryHTML(s) {
  return `
    <div class="pt-2 space-y-1 text-xs text-text-secondary">
      <div>Участников: <strong class="text-text-main">${escapeHtml(String(s.participant_count ?? 0))}</strong>
        · медиана: <strong class="text-text-main">${escapeHtml(s.median ?? '—')}</strong>
        · разброс: <strong class="text-text-main">${escapeHtml(s.spread ?? '—')}</strong>
      </div>
      ${s.note ? `<div>${escapeHtml(s.note)}</div>` : ''}
      ${(s.responses || []).map(r => `
        <div class="flex flex-wrap gap-2">
          <span class="text-text-main">${escapeHtml(r.participant)}</span>
          <span>${escapeHtml(r.value ?? '—')}</span>
          ${r.explanation ? `<span>${escapeHtml(r.explanation)}</span>` : ''}
          ${r.revision_reason ? `<span class="text-amber-400">правка: ${escapeHtml(r.revision_reason)}</span>` : ''}
        </div>
      `).join('')}
    </div>
  `;
}
