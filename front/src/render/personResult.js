function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function companyRow(company) {
  const status = company.status
    ? `<span class="text-xs ${String(company.status).toLowerCase().includes('действ') ? 'text-green-400' : 'text-amber-400'}">${escapeHtml(company.status)}</span>`
    : '';
  return `
    <div class="flex flex-col gap-1 py-2 border-b border-card-border last:border-b-0">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm font-medium text-text-main">${escapeHtml(company.name || '—')}</span>
        ${status}
      </div>
      <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-secondary">
        ${company.inn ? `<span>ИНН ${escapeHtml(company.inn)}</span>` : ''}
        ${company.ogrn ? `<span>ОГРН ${escapeHtml(company.ogrn)}</span>` : ''}
        ${company.registration_date ? `<span>рег. ${escapeHtml(company.registration_date)}</span>` : ''}
        ${company.okved ? `<span>ОКВЭД ${escapeHtml(company.okved)}</span>` : ''}
      </div>
      ${company.address ? `<div class="text-xs text-text-secondary">${escapeHtml(company.address)}</div>` : ''}
    </div>
  `;
}

function companyList(title, items) {
  if (!items?.length) return '';
  return `
    <div>
      <h4 class="text-xs text-text-secondary mb-1">${escapeHtml(title)} · ${items.length}</h4>
      <div class="bg-surface rounded-xl px-3 py-1">
        ${items.map(companyRow).join('')}
      </div>
    </div>
  `;
}

export function renderPersonLoadingHTML() {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6 slide-up">
      <div class="flex items-center gap-3">
        <div class="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
        <p class="text-sm text-text-secondary">Запрашиваем деловые связи физлица…</p>
      </div>
    </div>
  `;
}

export function renderPersonErrorHTML(message) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6 slide-up border border-red-800/40">
      <div class="flex items-start gap-3">
        <i data-lucide="alert-circle" class="w-5 h-5 text-red-400 shrink-0 mt-0.5"></i>
        <div>
          <h3 class="text-sm font-semibold text-text-main mb-1">Ошибка проверки физлица</h3>
          <p class="text-sm text-text-secondary">${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

/**
 * Модуль «Деловые связи физлица» (Checko person.md).
 * @param {object} person — нормализованный ответ API
 * @param {object|null} record — запись проверки (role, auto, …)
 */
export function renderPersonResultHTML(person, record = null) {
  if (!person) return '';

  const riskFactors = person.risk_factors || {};
  const riskChips = [];
  if (riskFactors.unfair_supplier) riskChips.push('Реестр недобросовестных поставщиков');
  if (riskFactors.mass_director) riskChips.push('Массовый руководитель');
  if (riskFactors.mass_founder) riskChips.push('Массовый учредитель');
  if (riskFactors.sanctioned) riskChips.push('Санкции в отношении физлица');
  const countries = riskFactors.sanctioned_countries || [];
  if (countries.length) riskChips.push(`Санкции стран: ${countries.join(', ')}`);

  const businesses = person.entrepreneurships || [];
  const trademarks = person.trademarks || [];
  const bankruptcies = person.bankruptcy_messages || [];

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" id="person-result-card-${escapeHtml(person.inn)}">
      <div class="p-6 border-b border-card-border flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-lg font-semibold text-text-main">${escapeHtml(person.full_name)}</h3>
            ${record?.role ? `
              <span class="px-2 py-1 rounded-lg text-xs bg-primary/[.18] text-primary">${escapeHtml(record.role)}</span>
            ` : ''}
            ${record?.auto ? `
              <span class="px-2 py-1 rounded-lg text-xs bg-[#383838] text-text-secondary">автопроверка</span>
            ` : ''}
          </div>
          <p class="text-sm text-text-secondary mt-1">
            ИНН: ${escapeHtml(person.inn)} · физическое лицо
          </p>
        </div>
        <div>
          ${riskChips.length
            ? `<span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-red-900/[.30] text-red-400 border border-red-800/40">Риск: требует внимания</span>`
            : `<span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-green-900/[.30] text-green-400 border border-green-800/40">Факторы риска не отмечены</span>`}
        </div>
      </div>

      <div class="p-6 space-y-5">
        ${companyList('Руководит организациями', person.managed_companies)}
        ${companyList('Учредитель в организациях', person.founded_companies)}

        ${businesses.length ? `
          <div>
            <h4 class="text-xs text-text-secondary mb-1">Индивидуальное предпринимательство · ${businesses.length}</h4>
            <div class="bg-surface rounded-xl px-3 py-1">
              ${businesses.map(ip => `
                <div class="flex flex-col gap-1 py-2 border-b border-card-border last:border-b-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-sm font-medium text-text-main">${escapeHtml(ip.name || 'ИП')}</span>
                    ${ip.status ? `<span class="text-xs text-text-secondary">${escapeHtml(ip.status)}</span>` : ''}
                  </div>
                  <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-secondary">
                    ${ip.ogrnip ? `<span>ОГРНИП ${escapeHtml(ip.ogrnip)}</span>` : ''}
                    ${ip.registration_date ? `<span>рег. ${escapeHtml(ip.registration_date)}</span>` : ''}
                    ${ip.termination_date ? `<span>прекращение ${escapeHtml(ip.termination_date)}</span>` : ''}
                    ${ip.okved ? `<span>ОКВЭД ${escapeHtml(ip.okved)}</span>` : ''}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        ${trademarks.length ? `
          <div>
            <h4 class="text-xs text-text-secondary mb-1">Товарные знаки · ${trademarks.length}</h4>
            <div class="bg-surface rounded-xl px-3 py-2 text-sm text-text-main">
              ${trademarks.map(t => `
                <div class="py-1 text-xs text-text-secondary">
                  №${escapeHtml(t.ID)}${t.ДатаРег ? ` · рег. ${escapeHtml(t.ДатаРег)}` : ''}${t.ДатаОконч ? ` · до ${escapeHtml(t.ДатаОконч)}` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        ${bankruptcies.length ? `
          <div>
            <h4 class="text-xs text-text-secondary mb-1">Сообщения ЕФРСБ · ${bankruptcies.length}</h4>
            <div class="bg-surface rounded-xl px-3 py-2">
              ${bankruptcies.map(b => `
                <div class="py-1 text-xs text-text-secondary">
                  ${escapeHtml(b.Тип || 'Сообщение')}${b.Дата ? ` · ${escapeHtml(b.Дата)}` : ''}${b.Дело ? ` · дело ${escapeHtml(b.Дело)}` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <div>
          <h4 class="text-xs text-text-secondary mb-2">Факторы риска</h4>
          ${riskChips.length ? `
            <div class="flex flex-wrap gap-2">
              ${riskChips.map(r => `
                <span class="px-3 py-1.5 rounded-xl text-xs font-medium bg-red-900/[.30] text-red-400 border border-red-800/40">
                  ${escapeHtml(r)}
                </span>
              `).join('')}
            </div>
          ` : `
            <p class="text-sm text-text-secondary">
              В полученных сведениях нет отмеченных факторов риска.
            </p>
          `}
        </div>
      </div>
    </div>
  `;
}

/**
 * Список карточек физлиц (авто + ручные проверки).
 * @param {object[]} records — записи с полем person / checkStatus
 */
export function renderPersonResultsList(records) {
  if (!records?.length) return '';
  return `
    <div class="space-y-4">
      ${records.map(record => {
        const status = record.checkStatus || record.status;
        if (status === 'no_inn') {
          return `
            <div class="bg-surface rounded-xl p-4 border border-card-border">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-medium text-text-main">${escapeHtml(record.name)}</p>
                  <p class="text-xs text-text-secondary mt-1">${escapeHtml((record.roles || [record.role]).filter(Boolean).join(', '))}</p>
                  <p class="text-xs text-amber-400 mt-2">${escapeHtml(record.findings || 'Автоматическая проверка недоступна: нет ИНН')}</p>
                </div>
                <span class="px-2 py-1 rounded-lg text-xs bg-amber-900/[.30] text-amber-400 shrink-0">без ИНН</span>
              </div>
            </div>
          `;
        }
        if (status === 'not_checked') {
          return `
            <div class="bg-surface rounded-xl p-4 border border-card-border">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-medium text-text-main">${escapeHtml(record.name)}</p>
                  <p class="text-xs text-text-secondary mt-1">
                    ${escapeHtml((record.roles || [record.role]).filter(Boolean).join(', '))}
                    ${record.inn ? ` · ИНН ${escapeHtml(record.inn)}` : ''}
                  </p>
                </div>
                <span class="px-2 py-1 rounded-lg text-xs bg-[#383838] text-text-secondary shrink-0">не проверялся</span>
              </div>
            </div>
          `;
        }
        if (status === 'Проверяется' || status === 'checking') {
          return `
            <div class="bg-card rounded-2xl shadow-soft p-4 slide-up">
              <div class="flex items-center gap-3">
                <div class="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full shrink-0"></div>
                <div>
                  <p class="text-sm font-medium text-text-main">${escapeHtml(record.name || record.inn)}</p>
                  <p class="text-xs text-text-secondary">ИНН ${escapeHtml(record.inn)} · проверяем…</p>
                </div>
              </div>
            </div>
          `;
        }
        if (status === 'Ошибка проверки' || status === 'error') {
          return `
            <div class="bg-card rounded-2xl shadow-soft p-4 slide-up border border-red-800/40">
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-start gap-3">
                  <i data-lucide="alert-circle" class="w-5 h-5 text-red-400 shrink-0 mt-0.5"></i>
                  <div>
                    <p class="text-sm font-medium text-text-main">${escapeHtml(record.name || record.inn)}</p>
                    <p class="text-xs text-text-secondary mt-1">
                      ИНН ${escapeHtml(record.inn)}
                      ${(record.roles || []).length ? ` · ${escapeHtml(record.roles.join(', '))}` : ''}
                    </p>
                    <p class="text-sm text-text-secondary mt-1">${escapeHtml(record.findings || 'Ошибка проверки')}</p>
                  </div>
                </div>
                ${record.inn ? `
                  <button
                    type="button"
                    class="person-retry-btn px-3 py-1.5 rounded-lg text-xs bg-surface border border-card-border text-text-secondary hover:text-text-main shrink-0"
                    data-inn="${escapeHtml(record.inn)}"
                  >
                    Повторить
                  </button>
                ` : ''}
              </div>
            </div>
          `;
        }
        return renderPersonResultHTML(record.person, record);
      }).join('')}
    </div>
  `;
}
