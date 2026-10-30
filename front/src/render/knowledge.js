/**
 * Knowledge UI blocks: evidence provenance + weak signals (Task2 §9, §12).
 * Pure HTML builders — no DOM side effects (testable).
 */

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

const VERIFICATION = {
  unreviewed: { text: 'не проверено', cls: 'bg-amber-900/[.30] text-amber-400' },
  supported: { text: 'подтверждено', cls: 'bg-green-900/[.30] text-green-400' },
  refuted: { text: 'опровергнуто', cls: 'bg-red-900/[.30] text-red-400' },
  needs_review: { text: 'на проверке', cls: 'bg-amber-900/[.30] text-amber-400' },
};

const CLAIM_TYPE = {
  fact: 'факт',
  interpretation: 'интерпретация',
  unverified_snippet: 'выдержка поиска',
  forecast: 'прогноз',
  calculation: 'расчёт',
};

function verificationBadge(status) {
  const v = VERIFICATION[status] || VERIFICATION.unreviewed;
  return `<span class="px-2 py-0.5 rounded-lg text-xs ${v.cls}">${escapeHtml(v.text)}</span>`;
}

/**
 * Sources with provenance for market / report blocks.
 * items: [{ id, title, url, quote, claim_type, verification_status, completeness, source_id }]
 */
export function renderEvidenceSourcesHTML(items, { title = 'Источники и доказательства', emptyText = 'Источники ещё не собраны.' } = {}) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    return `
      <div>
        <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">${escapeHtml(title)}</h3>
        <p class="text-sm text-text-secondary">${escapeHtml(emptyText)}</p>
      </div>
    `;
  }
  return `
    <div>
      <h3 class="text-xs uppercase tracking-wider text-text-secondary mb-2">${escapeHtml(title)}</h3>
      <ul class="space-y-2">
        ${list.slice(0, 8).map((e, i) => {
          const id = e.id || e.evidence_id || `src-${i}`;
          const claim = CLAIM_TYPE[e.claim_type] || CLAIM_TYPE[e.type] || e.claim_type || e.type || 'источник';
          return `
            <li class="bg-surface rounded-xl p-3" data-evidence-id="${escapeHtml(String(id))}">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="text-sm text-text-main font-medium">
                  ${e.url
                    ? `<a href="${escapeHtml(e.url)}" target="_blank" rel="noopener noreferrer" class="hover:text-primary transition-colors">${escapeHtml(e.title || e.name || String(id))}</a>`
                    : escapeHtml(e.title || e.name || String(id))}
                </div>
                <div class="flex flex-wrap items-center gap-1">
                  ${sourceBadge(e.source || e.source_id)}
                  ${readLevelBadge(e.read_level || (e.completeness === 'snippet_only' ? 'snippet_only' : undefined))}
                  ${verificationBadge(e.verification_status)}
                  <span class="px-2 py-0.5 rounded-lg text-xs bg-[#383838] text-text-secondary">${escapeHtml(String(claim))}</span>
                  ${e.completeness && e.completeness !== 'full' && e.completeness !== 'snippet_only'
                    ? `<span class="px-2 py-0.5 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">${escapeHtml(e.completeness)}</span>`
                    : ''}
                </div>
              </div>
              ${e.quote ? `<p class="text-xs text-text-secondary mt-1 line-clamp-2">${escapeHtml(e.quote)}</p>` : ''}
              ${e.source_id ? `<p class="text-xs text-text-secondary mt-1">Источник: ${escapeHtml(e.source_id)}</p>` : ''}
            </li>
          `;
        }).join('')}
      </ul>
      ${list.length > 8 ? `<p class="text-xs text-text-secondary mt-2">Ещё ${list.length - 8} источников.</p>` : ''}
    </div>
  `;
}

const EVENT_TYPE = {
  publication: 'публикация',
  trial: 'испытание',
  product_launch: 'выпуск продукта',
  partnership: 'партнёрство',
  procurement: 'закупка',
  requirement_change: 'изменение требований',
};

function hypothesisStatusBadge(status) {
  if (status === 'supported') return '<span class="px-2 py-0.5 rounded-lg text-xs bg-green-900/[.30] text-green-400">поддерживается</span>';
  if (status === 'rejected') return '<span class="px-2 py-0.5 rounded-lg text-xs bg-red-900/[.30] text-red-400">отклонена</span>';
  if (status === 'needs_more_data') return '<span class="px-2 py-0.5 rounded-lg text-xs bg-amber-900/[.30] text-amber-400">мало данных</span>';
  return '<span class="px-2 py-0.5 rounded-lg text-xs bg-[#383838] text-text-secondary">гипотеза</span>';
}

/**
 * Weak signals block: events + hypotheses from knowledge store (§11).
 */
export function renderKnowledgeSignalsHTML({ events = [], hypotheses = [], loading = false, error = '' } = {}) {
  if (loading) {
    return `
      <div class="bg-card rounded-2xl shadow-soft p-6">
        <h3 class="text-base font-semibold text-text-main mb-2">Сигналы базы знаний</h3>
        <div class="flex items-center gap-2 text-sm text-text-secondary">
          <span class="inline-block w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></span>
          Загрузка событий и гипотез…
        </div>
      </div>
    `;
  }
  if (error) {
    return `
      <div class="bg-card rounded-2xl shadow-soft p-6 border border-red-800/40">
        <h3 class="text-base font-semibold text-text-main mb-2">Сигналы базы знаний</h3>
        <p class="text-sm text-red-400">${escapeHtml(error)}</p>
      </div>
    `;
  }
  const evList = Array.isArray(events) ? events : [];
  const hypList = Array.isArray(hypotheses) ? hypotheses : [];
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6 space-y-5">
      <div>
        <h3 class="text-base font-semibold text-text-main mb-1">События</h3>
        <p class="text-xs text-text-secondary mb-3">
          Перепечатки одного события не считаются независимыми источниками.
        </p>
        ${evList.length ? `
          <ul class="space-y-2">
            ${evList.slice(0, 5).map(ev => `
              <li class="bg-surface rounded-xl p-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="text-sm text-text-main">
                    ${escapeHtml(EVENT_TYPE[ev.event_type] || ev.event_type)}: ${escapeHtml(ev.subject)}
                  </div>
                  <div class="text-xs text-text-secondary">
                    независимых источников: <strong class="text-text-main">${escapeHtml(String(ev.independent_sources ?? 1))}</strong>
                    ${ev.event_at ? ` · ${escapeHtml(String(ev.event_at))}` : ''}
                  </div>
                </div>
                ${ev.notes ? `<p class="text-xs text-text-secondary mt-1">${escapeHtml(ev.notes)}</p>` : ''}
              </li>
            `).join('')}
          </ul>
          ${evList.length > 5 ? `<p class="text-xs text-text-secondary mt-2">Ещё ${evList.length - 5} событий.</p>` : ''}
        ` : '<p class="text-sm text-text-secondary">События не зафиксированы.</p>'}
      </div>
      <div>
        <h3 class="text-base font-semibold text-text-main mb-1">Гипотезы</h3>
        <p class="text-xs text-text-secondary mb-3">
          Неподтверждённые гипотезы показываются отдельно и не становятся фактами.
        </p>
        ${hypList.length ? `
          <ul class="space-y-2">
            ${hypList.slice(0, 5).map(h => `
              <li class="bg-surface rounded-xl p-3">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="text-sm text-text-main">${escapeHtml(h.statement)}</div>
                  ${hypothesisStatusBadge(h.status)}
                </div>
                ${(h.limitations || []).length ? `
                  <p class="text-xs text-amber-400 mt-1">Ограничения: ${escapeHtml(h.limitations.join('; '))}</p>
                ` : ''}
                ${(h.questions || []).length ? `
                  <p class="text-xs text-text-secondary mt-1">Вопросы: ${escapeHtml(h.questions.join('; '))}</p>
                ` : ''}
                ${h.coverage_limited ? '<p class="text-xs text-amber-400 mt-1">Сравнение периодов ограничено охватом.</p>' : ''}
              </li>
            `).join('')}
          </ul>
        ` : '<p class="text-sm text-text-secondary">Гипотезы не сформированы.</p>'}
      </div>
    </div>
  `;
}

/**
 * Compact search result list for knowledge retrieval (§12).
 * Each hit shows source + read_level (аннотация / полный текст).
 */
export function readLevelBadge(readLevel) {
  const map = {
    full_text: { label: 'полный текст', cls: 'bg-emerald-900/[.35] text-emerald-300' },
    html_or_text: { label: 'текст/HTML', cls: 'bg-emerald-900/[.35] text-emerald-300' },
    abstract_only: { label: 'аннотация', cls: 'bg-sky-900/[.35] text-sky-300' },
    snippet_only: { label: 'фрагмент', cls: 'bg-amber-900/[.35] text-amber-300' },
    unknown: { label: 'не прочитано', cls: 'bg-zinc-800 text-zinc-400' },
    unknown_until_parse: { label: 'не прочитано', cls: 'bg-zinc-800 text-zinc-400' },
  };
  const m = map[readLevel] || map.unknown;
  return `<span class="px-2 py-0.5 rounded text-[10px] ${m.cls}">${escapeHtml(m.label)}</span>`;
}

export function sourceBadge(source) {
  if (!source) return '';
  return `<span class="px-2 py-0.5 rounded text-[10px] bg-violet-900/[.35] text-violet-300">${escapeHtml(String(source))}</span>`;
}

export function renderKnowledgeSearchResultsHTML(result = {}) {
  const items = result.items || [];
  const limit = result.limitations || [];
  if (!items.length) {
    return `
      <div class="bg-surface rounded-xl p-4">
        <p class="text-sm text-text-secondary">
          ${escapeHtml(result.empty_reason === 'no_evidence_in_allowed_corpus'
            ? 'В разрешённом корпусе нет подходящих доказательств.'
            : 'Ничего не найдено.')}
        </p>
        ${limit.length ? `<p class="text-xs text-amber-400 mt-2">${escapeHtml(limit.join('; '))}</p>` : ''}
      </div>
    `;
  }
  return `
    <div class="space-y-2">
      ${items.map(i => `
        <div class="bg-surface rounded-xl p-3" data-chunk-id="${escapeHtml(String(i.chunk_id || ''))}">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-sm text-text-main font-medium">${escapeHtml(i.title || 'Документ')}</div>
            <div class="flex items-center gap-1 flex-wrap">
              ${sourceBadge(i.source)}
              ${readLevelBadge(i.read_level)}
              ${verificationBadge(i.verification_status)}
              <span class="text-xs text-text-secondary">${escapeHtml(i.origin || '')}</span>
            </div>
          </div>
          <p class="text-xs text-text-secondary mt-1">${escapeHtml(i.excerpt || '')}</p>
          ${i.source_url ? `<a class="text-xs text-primary mt-1 inline-block" href="${escapeHtml(i.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(i.source_url)}</a>` : ''}
        </div>
      `).join('')}
      ${limit.length ? `<p class="text-xs text-amber-400">${escapeHtml(limit.join('; '))}</p>` : ''}
    </div>
  `;
}
