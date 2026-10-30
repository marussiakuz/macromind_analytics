import { portfolioCompanies } from '../data/mockData.js';
import { state } from '../state.js';

function alertStyle(type) {
  if (type === 'danger') return 'text-red-400 bg-red-900/[.15] border border-red-900/[.30]';
  if (type === 'warning') return 'text-amber-400 bg-amber-900/[.15] border border-amber-900/[.30]';
  return 'text-text-secondary bg-[#333] border border-card-border';
}

function alertIcon(type) {
  if (type === 'danger') return 'alert-circle';
  if (type === 'warning') return 'clock';
  return 'badge-check';
}

function modalTabClass(tabId) {
  const active = state.companyModalTab === tabId;
  return active
    ? 'company-modal-tab px-5 py-4 text-sm font-semibold text-primary border-b-2 border-primary'
    : 'company-modal-tab px-5 py-4 text-sm font-medium text-text-secondary border-b-2 border-transparent hover:text-text-main transition-colors';
}

function renderModalOverview(company) {
  return `
    <div class="grid grid-cols-3 gap-6">
      <div class="col-span-2 space-y-6">
        <!-- AI Summary -->
        <div class="bg-card p-6 rounded-2xl border border-card-border">
          <h3 class="font-semibold text-text-main mb-3 flex items-center gap-2">
            <i data-lucide="sparkles" class="w-4 h-4 text-primary"></i>
            AI Резюме статуса
          </h3>
          <p class="text-sm text-text-secondary leading-relaxed">${company.aiSummary}</p>
        </div>

        <!-- Events timeline -->
        <div class="bg-card p-6 rounded-2xl border border-card-border">
          <h3 class="font-semibold text-text-main mb-5">Хронология событий</h3>
          <div class="space-y-6 relative before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-0.5 before:bg-card-border">
            ${company.events.map(ev => `
              <div class="relative pl-8">
                <div class="absolute left-0 top-1 w-4 h-4 ${ev.dotColor} rounded-full border-2 border-surface shadow-sm"></div>
                <div class="text-xs text-text-secondary mb-1">${ev.date} · ${ev.source}</div>
                <div class="text-sm font-semibold text-text-main">${ev.title}</div>
                <div class="text-sm text-text-secondary mt-1">${ev.description}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>

      <div class="space-y-6">
        <!-- Quick actions -->
        <div class="bg-card p-6 rounded-2xl border border-card-border">
          <h3 class="font-semibold text-text-main mb-4">Быстрые действия</h3>
          <div class="space-y-3">
            <button class="w-full py-2 px-4 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2">
              <i data-lucide="file-text" class="w-4 h-4"></i> Создать отчёт для LP
            </button>
            <button class="w-full py-2 px-4 bg-card border border-card-border text-text-main rounded-xl text-sm font-medium hover:bg-[#333] transition-all flex items-center justify-center gap-2">
              <i data-lucide="search" class="w-4 h-4"></i> Проверить контрагентов
            </button>
            <button class="w-full py-2 px-4 bg-card border border-card-border text-text-main rounded-xl text-sm font-medium hover:bg-[#333] transition-all flex items-center justify-center gap-2">
              <i data-lucide="history" class="w-4 h-4"></i> История переписки
            </button>
          </div>
        </div>

        <!-- Key metrics -->
        <div class="bg-card p-6 rounded-2xl border border-card-border">
          <h3 class="font-semibold text-text-main mb-4">Ключевые метрики</h3>
          <div class="space-y-4">
            ${company.metrics.map(m => `
              <div>
                <div class="text-xs text-text-secondary">${m.label}</div>
                <div class="text-lg font-bold ${m.positive === true ? 'text-green-400' : m.positive === false ? 'text-red-400' : 'text-text-main'}">${m.value}</div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderModalDocuments(company) {
  return `
    <div class="bg-card rounded-2xl border border-card-border overflow-hidden">
      <div class="px-6 py-4 border-b border-card-border flex justify-between items-center">
        <h3 class="font-semibold text-text-main">Документы проекта (Data Room)</h3>
        <button class="text-xs text-primary font-medium hover:underline">Загрузить новый</button>
      </div>
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="bg-surface">
            <th class="px-6 py-3 text-text-secondary font-medium">Название файла</th>
            <th class="px-6 py-3 text-text-secondary font-medium">Тип</th>
            <th class="px-6 py-3 text-text-secondary font-medium">Дата загрузки</th>
            <th class="px-6 py-3 text-text-secondary font-medium">Статус</th>
            <th class="px-6 py-3 text-text-secondary font-medium">Действия</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-card-border">
          ${company.documents.map(doc => `
            <tr class="hover:bg-[#333] transition-colors">
              <td class="px-6 py-4 flex items-center gap-3">
                <i data-lucide="${doc.icon}" class="w-4 h-4 ${doc.iconColor} shrink-0"></i>
                <span class="font-medium text-text-main">${doc.name}</span>
              </td>
              <td class="px-6 py-4 text-text-secondary">${doc.type}</td>
              <td class="px-6 py-4 text-text-secondary">${doc.date}</td>
              <td class="px-6 py-4">
                <span class="px-2 py-1 rounded-full text-xs font-medium ${doc.statusClass}">${doc.status}</span>
              </td>
              <td class="px-6 py-4">
                <button class="text-text-secondary hover:text-primary transition-colors">
                  <i data-lucide="download" class="w-4 h-4"></i>
                </button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderModalHistory(company) {
  return `
    <div class="bg-card rounded-2xl border border-card-border p-6">
      <h3 class="font-semibold text-text-main mb-6">Решения Инвестиционного Комитета</h3>
      <div class="space-y-6">
        ${company.icDecisions.map(d => `
          <div class="border-l-4 ${d.borderColor} pl-5 py-1">
            <div class="flex justify-between items-start mb-1">
              <h4 class="font-semibold text-text-main">${d.title}</h4>
              <span class="text-xs text-text-secondary shrink-0 ml-4">${d.date}</span>
            </div>
            <p class="text-sm text-text-secondary">${d.description}</p>
            ${d.note ? `
              <div class="mt-3 text-sm text-text-secondary bg-surface p-3 rounded-xl border border-card-border">
                <strong class="text-text-main">Особое мнение:</strong> ${d.note}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderModalObligations(company) {
  return `
    <div class="bg-card rounded-2xl border border-card-border p-6">
      <h3 class="font-semibold text-text-main mb-5">Обязательства по договору SHA</h3>
      <ul class="space-y-3">
        ${company.shaObligations.map(ob => `
          <li class="flex items-start gap-3 p-4 bg-surface rounded-xl border border-card-border">
            <i data-lucide="check-square" class="w-5 h-5 text-primary mt-0.5 shrink-0"></i>
            <div>
              <p class="text-sm font-semibold text-text-main">${ob.title}</p>
              <p class="text-xs text-text-secondary mt-1">${ob.description}</p>
            </div>
          </li>
        `).join('')}
      </ul>
    </div>
  `;
}

function renderCompanyModal(company) {
  let tabContent = '';
  switch (state.companyModalTab) {
    case 'overview':     tabContent = renderModalOverview(company); break;
    case 'documents':    tabContent = renderModalDocuments(company); break;
    case 'history':      tabContent = renderModalHistory(company); break;
    case 'obligations':  tabContent = renderModalObligations(company); break;
    default:             tabContent = renderModalOverview(company);
  }

  return `
    <div id="company-modal-overlay" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center backdrop-blur-sm">
      <div class="bg-surface w-full max-w-5xl h-[88vh] rounded-2xl shadow-large flex flex-col overflow-hidden" style="animation: slideUp 0.25s ease-out">
        <!-- Modal header -->
        <div class="px-8 py-6 border-b border-card-border flex justify-between items-start bg-card shrink-0">
          <div class="flex gap-4 items-start">
            <div class="w-16 h-16 ${company.modalBg} rounded-2xl flex items-center justify-center text-white font-bold text-2xl shrink-0">${company.shortName}</div>
            <div>
              <h2 class="text-2xl font-bold text-text-main">${company.name}</h2>
              <div class="flex gap-2 mt-2 flex-wrap">
                <span class="px-2 py-1 bg-[#333] text-text-secondary text-xs rounded-lg font-medium">ИНН: ${company.inn}</span>
                ${company.tags.map(t => `<span class="px-2 py-1 bg-primary/[.18] text-primary text-xs rounded-lg font-medium">${t}</span>`).join('')}
              </div>
            </div>
          </div>
          <button id="company-modal-close" class="p-2 hover:bg-[#333] rounded-xl transition-colors shrink-0">
            <i data-lucide="x" class="w-5 h-5 text-text-secondary"></i>
          </button>
        </div>

        <!-- Modal tabs -->
        <div class="flex border-b border-card-border px-8 bg-card shrink-0">
          <button class="${modalTabClass('overview')}" data-modal-tab="overview">Обзор & Риски</button>
          <button class="${modalTabClass('documents')}" data-modal-tab="documents">Документы (Data Room)</button>
          <button class="${modalTabClass('history')}" data-modal-tab="history">История решений ИК</button>
          <button class="${modalTabClass('obligations')}" data-modal-tab="obligations">Обязательства</button>
        </div>

        <!-- Modal content -->
        <div class="flex-1 overflow-y-auto p-8 bg-surface/[.50]">
          ${tabContent}
        </div>
      </div>
    </div>
  `;
}

export function renderCompanies() {
  return `
    <div class="flex-1 flex flex-col gap-6 slide-up">
      <div>
        <h1 class="text-2xl font-semibold text-text-main mb-2">Портфельные компании</h1>
        <p class="text-text-secondary">Компании в портфеле фонда · нажмите на карточку для детального просмотра</p>
      </div>

      <div class="grid grid-cols-3 gap-6">
        ${portfolioCompanies.map(company => `
          <div
            class="bg-card rounded-2xl shadow-soft p-6 cursor-pointer group company-card card-hover"
            data-company-id="${company.id}"
          >
            <div class="flex justify-between items-start mb-4">
              <div class="w-12 h-12 ${company.colorClass} rounded-xl flex items-center justify-center font-bold text-xl">${company.shortName}</div>
              <span class="px-2 py-1 bg-primary/[.18] text-primary text-xs font-medium rounded-full">${company.statusLabel}</span>
            </div>
            <h3 class="font-bold text-text-main text-lg group-hover:text-primary transition-colors">${company.name}</h3>
            <p class="text-sm text-text-secondary mt-1 line-clamp-2">${company.description}</p>

            <div class="mt-4 pt-4 border-t border-card-border space-y-2">
              <div class="flex justify-between text-sm">
                <span class="text-text-secondary">Доля фонда:</span>
                <span class="font-semibold text-text-main">${company.fundShare}</span>
              </div>
              <div class="flex justify-between text-sm">
                <span class="text-text-secondary">Дата входа:</span>
                <span class="font-semibold text-text-main">${company.entryDate}</span>
              </div>
              <div class="flex justify-between text-sm">
                <span class="text-text-secondary">Выручка (LTM):</span>
                <span class="font-semibold text-text-main">${company.metrics[0].value}</span>
              </div>
            </div>

            <div class="mt-4 flex items-center gap-2 text-xs ${alertStyle(company.alertType)} px-3 py-2 rounded-lg">
              <i data-lucide="${alertIcon(company.alertType)}" class="w-3 h-3 shrink-0"></i>
              ${company.alertLabel}
            </div>
          </div>
        `).join('')}
      </div>

      ${state.selectedCompany ? renderCompanyModal(state.selectedCompany) : ''}
    </div>
  `;
}
