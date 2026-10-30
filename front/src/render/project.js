import { mockDocuments, mockSummary } from '../data/mockData.js';
import { state } from '../state.js';
import {
  formatDate,
  getRiskColor,
  getRiskIcon,
  getStatusColor,
  getVerificationBadge,
  getRiskCategoryLabel,
  renderContentWithCitations,
} from '../utils/helpers.js';
import { renderHeader } from './header.js';
import { renderNotificationsHTML } from '../notifications.js';
import { renderFeedbackModal } from './feedback.js';
import { renderGraph, destroyGraph, renderFiltersHTML, renderStatsHTML } from './graph.js';
import { renderMarketSummaryHTML } from './market.js';
import { marketState } from '../market/state.js';
import { loadDealMarketSummary } from '../market/events.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function renderDocumentsTab() {
  const projectDocs = mockDocuments.filter((d) => d.projectId === state.selectedProject.id);
  return `
    <div>
      <h3 class="text-lg font-semibold text-text-main mb-4">Загруженные документы</h3>
      <div class="space-y-3">
        ${projectDocs
          .map(
            (doc, index) => `
          <div class="stagger-item flex items-center justify-between p-4 border border-card-border rounded-xl" style="animation-delay: ${index * 0.05}s">
            <div class="flex items-center gap-4">
              <div class="w-12 h-12 rounded-xl ${doc.status === 'Загружено' ? 'bg-green-900/[.30]' : 'bg-surface'} flex items-center justify-center">
                <i data-lucide="file" class="w-6 h-6 ${doc.status === 'Загружено' ? 'text-green-400' : 'text-text-secondary'}"></i>
              </div>
              <div>
                <div class="font-medium text-text-main">${doc.name}</div>
                <div class="text-sm text-text-secondary">${doc.type} • ${doc.uploadedAt ? formatDate(doc.uploadedAt) : 'Не загружен'}</div>
              </div>
            </div>
            <div class="flex items-center gap-3">
              ${
                doc.validated
                  ? '<span class="px-3 py-1 bg-green-900/[.30] text-green-400 text-sm rounded-full font-medium"><i data-lucide="check" class="w-3 h-3 inline mr-1"></i>Проверено</span>'
                  : '<span class="px-3 py-1 bg-amber-900/[.30] text-amber-400 text-sm rounded-full font-medium"><i data-lucide="clock" class="w-3 h-3 inline mr-1"></i>На проверке</span>'
              }
              <button type="button" class="p-2 hover:bg-[#222222] rounded-lg transition-colors">
                <i data-lucide="download" class="w-4 h-4 text-text-secondary"></i>
              </button>
            </div>
          </div>
        `
          )
          .join('')}
      </div>
    </div>
  `;
}

function renderSummaryTab() {
  return `
    <div class="max-w-4xl">
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-semibold text-text-main flex items-center gap-2">
          <i data-lucide="sparkles" class="w-5 h-5 text-secondary"></i>
          AI Summary
        </h3>
        <div class="flex items-center gap-2">
          <span class="text-sm text-text-secondary">Сгенерировано:</span>
          <span class="text-sm font-medium text-text-main">${formatDate(new Date().toISOString())}</span>
        </div>
      </div>
      <div class="space-y-6">
        ${mockSummary.sections
          .map(
            (section, index) => `
          <div class="stagger-item border border-card-border rounded-xl p-5" style="animation-delay: ${index * 0.08}s">
            <div class="flex items-center justify-between mb-3">
              <h4 class="font-semibold text-text-main">${section.title}</h4>
              ${getVerificationBadge(section.verification)}
            </div>
            <div class="text-text-secondary leading-relaxed">${renderContentWithCitations(section.content)}</div>
            ${
              section.sources.length > 0
                ? `
              <div class="mt-3 flex flex-wrap gap-2">
                ${section.sources
                  .map(
                    (source) => `
                  <a href="${source.url}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2 py-1 bg-surface text-xs text-text-secondary rounded hover:bg-primary-light hover:text-primary transition-colors">
                    <i data-lucide="external-link" class="w-3 h-3"></i>
                    Источник ${source.id}
                  </a>
                `
                  )
                  .join('')}
              </div>
            `
                : ''
            }
          </div>
        `
          )
          .join('')}
      </div>
      <div class="mt-8 flex gap-3">
        <button type="button" class="btn-primary px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium">
          <i data-lucide="file-text" class="w-4 h-4 inline mr-2"></i>Экспорт в .docx
        </button>
        <button type="button" class="btn-primary px-4 py-2 bg-secondary hover:bg-secondary-hover text-white rounded-lg font-medium">
          <i data-lucide="file" class="w-4 h-4 inline mr-2"></i>Экспорт в .pdf
        </button>
      </div>
    </div>
  `;
}

function renderRisksTab() {
  return `
    <div>
      <h3 class="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
        <i data-lucide="alert-triangle" class="w-5 h-5 text-red-400"></i>
        Выявленные риски
      </h3>
      <div class="space-y-4">
        ${mockSummary.risks
          .map(
            (risk, index) => `
          <div class="stagger-item flex items-start gap-4 p-4 border rounded-xl ${getRiskColor(risk.severity)}" style="animation-delay: ${index * 0.1}s">
            <div class="text-2xl">${getRiskIcon(risk.severity)}</div>
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-semibold">${getRiskCategoryLabel(risk.category)}</span>
                <span class="px-2 py-0.5 bg-white/[.07] rounded text-xs font-medium">${risk.severity === 'high' ? 'Высокий' : risk.severity === 'medium' ? 'Средний' : 'Низкий'}</span>
              </div>
              <p class="text-sm opacity-90">${risk.description}</p>
            </div>
            <button type="button" class="p-2 hover:bg-[#363636]/[.07] rounded-lg transition-colors">
              <i data-lucide="more-horizontal" class="w-4 h-4"></i>
            </button>
          </div>
        `
          )
          .join('')}
      </div>
      <div class="mt-8 p-4 bg-primary/[.10] rounded-xl">
        <div class="flex items-start gap-3">
          <i data-lucide="info" class="w-5 h-5 text-primary mt-0.5"></i>
          <div>
            <h4 class="font-medium text-text-main mb-1">Рекомендация аналитика</h4>
            <p class="text-sm text-primary">Рекомендуется запросить у стартапа переоформление товарного знака на юридическое лицо перед следующим этапом Due Diligence.</p>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderCommentsTab() {
  return `
    <div>
      <h3 class="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
        <i data-lucide="message-square" class="w-5 h-5 text-primary"></i>
        Комментарии команды
      </h3>
      <div class="space-y-4 mb-6">
        <div class="flex gap-3">
          <div class="w-10 h-10 rounded-full bg-primary-light flex items-center justify-center text-primary font-semibold">ИП</div>
          <div class="flex-1">
            <div class="bg-card border border-card-border rounded-xl p-4">
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-text-main">Иван Петров</span>
                <span class="text-sm text-text-secondary">2 часа назад</span>
              </div>
              <p class="text-text-secondary">Проект выглядит перспективно. Технология интересная, но нужно проверить патентную чистоту.</p>
            </div>
          </div>
        </div>
        <div class="flex gap-3">
          <div class="w-10 h-10 rounded-full bg-secondary-light flex items-center justify-center text-secondary font-semibold">АС</div>
          <div class="flex-1">
            <div class="bg-card border border-card-border rounded-xl p-4">
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-text-main">Анна Смирнова</span>
                <span class="text-sm text-text-secondary">5 часов назад</span>
              </div>
              <p class="text-text-secondary">Финансовая модель требует доработки. Запросила дополнительные данные по unit-экономике.</p>
            </div>
          </div>
        </div>
      </div>
      <div class="flex gap-3">
        <div class="w-10 h-10 rounded-full bg-[#484848] flex items-center justify-center text-text-secondary font-semibold">Вы</div>
        <div class="flex-1">
          <textarea class="input-field w-full px-4 py-3 rounded-xl focus:outline-none resize-none" rows="3" placeholder="Добавить комментарий..."></textarea>
          <div class="flex justify-end mt-2">
            <button type="button" class="btn-primary px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium">
              Отправить
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderGraphTab() {
  const project = state.selectedProject;
  const defaultInn = project?.inn || '';
  return `
    <div>
      <div class="flex items-center gap-3 mb-4">
        <h3 class="text-lg font-semibold text-text-main flex items-center gap-2">
          <i data-lucide="network" class="w-5 h-5 text-primary"></i>
          Граф связей
        </h3>
        <div class="flex items-center gap-2 ml-4">
          <input type="text" id="graph-inn-input" value="${defaultInn}"
            class="input-field px-3 py-1.5 rounded-lg text-sm w-36"
            placeholder="ИНН компании" />
          <input type="text" id="graph-website-input"
            class="input-field px-3 py-1.5 rounded-lg text-sm w-48"
            placeholder="Сайт (необязательно)" />
          <button type="button" id="graph-load-btn"
            class="px-4 py-1.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors">
            <i data-lucide="search" class="w-3 h-3 inline mr-1"></i>Загрузить
          </button>
        </div>
        <div class="flex items-center gap-3 ml-auto">
          <div id="graph-stats"></div>
          <button type="button" id="graph-toggle-physics" class="px-3 py-1.5 text-xs bg-surface hover:bg-[#333] rounded-lg transition-colors text-text-secondary">
            <i data-lucide="zap" class="w-3 h-3 inline mr-1"></i>Физика
          </button>
          <button type="button" id="graph-fit" class="px-3 py-1.5 text-xs bg-surface hover:bg-[#333] rounded-lg transition-colors text-text-secondary">
            <i data-lucide="maximize" class="w-3 h-3 inline mr-1"></i>Вписать
          </button>
        </div>
      </div>
      <div class="flex gap-4">
        <div class="w-48 flex-shrink-0">
          <div class="bg-surface rounded-xl p-3">
            <h4 class="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Фильтры</h4>
            <div id="graph-filters" class="space-y-2"></div>
          </div>
        </div>
        <div class="flex-1">
          <div id="graph-container" class="bg-surface rounded-xl border border-card-border" style="height: 500px;"></div>
        </div>
      </div>
      <div id="graph-loading" class="hidden flex items-center justify-center py-12">
        <div class="text-center">
          <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3"></div>
          <p class="text-sm text-text-secondary">Загрузка графа...</p>
        </div>
      </div>
      <div id="graph-error" class="hidden p-4 bg-red-900/20 rounded-xl">
        <p class="text-sm text-red-400">Не удалось загрузить граф. API недоступен.</p>
      </div>
    </div>
  `;
}

function renderTabContent() {
  switch (state.activeTab) {
    case 'documents':
      return renderDocumentsTab();
    case 'summary':
      return renderSummaryTab();
    case 'market':
      return renderProjectMarketTab();
    case 'risks':
      return renderRisksTab();
    case 'comments':
      return renderCommentsTab();
    case 'graph':
      return renderGraphTab();
    default:
      return '';
  }
}

function renderProjectMarketTab() {
  const project = state.selectedProject;
  const summary = marketState.dealSummary;
  if (marketState.dealLoading) {
    return `
      <div>
        <h3 class="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
          <i data-lucide="bar-chart-3" class="w-5 h-5 text-primary"></i>
          Рынок и конкуренты
          <div class="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full"></div>
        </h3>
        <p class="text-sm text-text-secondary">Загружаем привязанное исследование…</p>
      </div>
    `;
  }
  return `
    <div>
      <h3 class="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
        <i data-lucide="bar-chart-3" class="w-5 h-5 text-primary"></i>
        Рынок и конкуренты
      </h3>
      <p class="text-sm text-text-secondary mb-4">
        Итоговое исследование связано с заявкой. Утверждения основателей хранятся отдельно от проверенных выводов.
      </p>
      ${summary
        ? renderMarketSummaryHTML(summary, {
            companyName: project?.name,
            inn: project?.inn,
          })
        : `
          <div class="bg-card rounded-2xl shadow-soft p-6">
            <p class="text-sm text-text-secondary">
              ${escapeHtml(marketState.dealError || 'Анализ рынка для этой заявки не выполнен.')}
            </p>
            <p class="text-xs text-text-secondary mt-2">
              Исследование привязывается по ИНН (${escapeHtml(project?.inn || '—')}) из раздела «Проверить юр. лицо».
            </p>
          </div>
        `}
    </div>
  `;
}

export function renderProjectCard() {
  const project = state.selectedProject;
  return `
    <div class="min-h-screen bg-surface">
      ${renderHeader()}
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div class="flex items-center gap-4 mb-6 slide-up">
          <button type="button" id="back-to-fund" class="p-2 hover:bg-card rounded-lg transition-colors">
            <i data-lucide="arrow-left" class="w-5 h-5 text-text-secondary"></i>
          </button>
          <div>
            <h1 class="text-2xl font-semibold text-text-main">${project.name}</h1>
            <p class="text-text-secondary">${project.description}</p>
          </div>
          <div class="ml-auto flex items-center gap-3">
            <span class="px-4 py-2 ${getStatusColor(project.status)} rounded-full text-sm font-medium">${project.status}</span>
            <button type="button" id="export-summary" class="btn-primary px-4 py-2 bg-secondary hover:bg-secondary-hover text-white rounded-lg font-medium">
              <i data-lucide="download" class="w-4 h-4 inline mr-2"></i>Выгрузить полный отчёт
            </button>
            <button type="button" id="send-feedback" class="btn-primary px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium">
              <i data-lucide="message-circle" class="w-4 h-4 inline mr-2"></i>Ответ стартапу
            </button>
          </div>
        </div>
        <div class="grid grid-cols-4 gap-4 mb-8 slide-up" style="animation-delay: 0.1s">
          <div class="bg-card rounded-xl shadow-soft p-4">
            <div class="text-sm text-text-secondary mb-1">Индустрия</div>
            <div class="font-semibold text-text-main">${project.industry}</div>
          </div>
          <div class="bg-card rounded-xl shadow-soft p-4">
            <div class="text-sm text-text-secondary mb-1">Стадия</div>
            <div class="font-semibold text-text-main">${project.stage_funding}</div>
          </div>
          <div class="bg-card rounded-xl shadow-soft p-4">
            <div class="text-sm text-text-secondary mb-1">Команда</div>
            <div class="font-semibold text-text-main">${project.team_size} человек</div>
          </div>
          <div class="bg-card rounded-xl shadow-soft p-4">
            <div class="text-sm text-text-secondary mb-1">Прогресс документов</div>
            <div class="font-semibold text-text-main">${project.documentsUploaded}/${project.documentsRequired}</div>
          </div>
        </div>
        <div class="bg-card rounded-2xl shadow-soft slide-up" style="animation-delay: 0.2s">
          <div class="border-b border-card-border">
            <div class="flex">
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'documents' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="documents">
                <i data-lucide="file-text" class="w-4 h-4 inline mr-2"></i>Документы
              </button>
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'summary' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="summary">
                <i data-lucide="sparkles" class="w-4 h-4 inline mr-2"></i>AI Summary
              </button>
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'market' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="market">
                <i data-lucide="bar-chart-3" class="w-4 h-4 inline mr-2"></i>Рынок
              </button>
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'risks' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="risks">
                <i data-lucide="alert-triangle" class="w-4 h-4 inline mr-2"></i>Риски
              </button>
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'comments' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="comments">
                <i data-lucide="message-square" class="w-4 h-4 inline mr-2"></i>Комментарии
              </button>
              <button type="button" class="tab-btn px-6 py-4 text-sm font-medium transition-all ${state.activeTab === 'graph' ? 'tab-active' : 'text-text-secondary hover:text-text-main'}" data-tab="graph">
                <i data-lucide="network" class="w-4 h-4 inline mr-2"></i>Граф связей
              </button>
            </div>
          </div>
          <div class="p-6">
            ${renderTabContent()}
          </div>
        </div>
      </div>
      ${renderNotificationsHTML()}
      ${renderFeedbackModal()}
    </div>
  `;
}
