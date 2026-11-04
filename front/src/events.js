import { mockProjects, portfolioCompanies } from './data/mockData.js';
import { showNotification } from './notifications.js';
import { state } from './state.js';
import { persistFromAppState } from './checkHistoryStore.js';
import { createIcons, icons } from 'lucide';
import { renderGraph, destroyGraph, togglePhysics, fitGraph, renderFiltersHTML, renderStatsHTML } from './render/graph.js';
import { renderCandidates, renderProfileReport } from './render/competency.js';
import { completeCompanyCheck } from './api/counterparty.js';
import { completePersonCheck, extractPersonInns, checkPersonsFromCompany, selectAutoBatch, MAX_AUTO_PERSON_CHECKS } from './api/person.js';
import { searchCompanies } from './api/companySearch.js';
import { fetchCompanyFinances } from './api/companyFinances.js';
import { fetchCompanyTimeline } from './api/companyTimeline.js';
import {
  REGISTRY_SECTIONS,
  fetchCompanyRegistry,
  fetchContractsRegistry,
} from './api/companyRegistry.js';
import { setupMarketListeners, loadMarketSummaryForInn, resetMarketState, downloadMarketReport, runAutoMarketAnalysis } from './market/events.js';
import { marketState } from './market/state.js';

// API base URL (adjust for production)
const API_BASE = 'http://localhost:8000';
const PEOPLE_API_BASE = 'http://localhost:8001';

/**
 * Загрузить и отрисовать граф связей компании.
 *
 * @param {string} inn — ИНН компании
 * @param {string|null} website — сайт (необязательно)
 */
async function loadAndRenderGraph(inn, website = null) {
  const container = document.getElementById('graph-container');
  const loading = document.getElementById('graph-loading');
  const error = document.getElementById('graph-error');
  const filtersDiv = document.getElementById('graph-filters');
  const statsDiv = document.getElementById('graph-stats');

  if (!container || !inn) return;

  // Show loading
  container.classList.add('hidden');
  if (loading) loading.classList.remove('hidden');
  if (error) error.classList.add('hidden');

  try {
    // Fetch graph from API
    let url = `${API_BASE}/api/v1/graph/${inn}`;
    if (website) {
      url += `?website=${encodeURIComponent(website)}`;
    }
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    // Hide loading, show container
    if (loading) loading.classList.add('hidden');
    container.classList.remove('hidden');

    // Render stats
    if (statsDiv) {
      statsDiv.innerHTML = renderStatsHTML(data.stats);
    }

    // Render filters
    if (filtersDiv) {
      filtersDiv.innerHTML = renderFiltersHTML(data.graph);

      // Add filter event listeners
      filtersDiv.querySelectorAll('.graph-filter-checkbox').forEach((cb) => {
        cb.addEventListener('change', () => {
          const visibleTypes = Array.from(
            filtersDiv.querySelectorAll('.graph-filter-checkbox:checked')
          ).map((el) => el.getAttribute('data-filter-type'));

          // Re-render with filtered data
          const filteredNodes = data.graph.nodes.filter((n) => visibleTypes.includes(n.type));
          const visibleIds = new Set(filteredNodes.map((n) => n.id));
          const filteredEdges = data.graph.edges.filter(
            (e) => visibleIds.has(e.from) && visibleIds.has(e.to)
          );
          renderGraph(container, { nodes: filteredNodes, edges: filteredEdges });
        });
      });
    }

    // Render graph
    renderGraph(container, data.graph);

    // Physics toggle
    let physicsEnabled = true;
    const physicsBtn = document.getElementById('graph-toggle-physics');
    if (physicsBtn) {
      physicsBtn.addEventListener('click', () => {
        physicsEnabled = !physicsEnabled;
        togglePhysics(physicsEnabled);
        physicsBtn.innerHTML = physicsEnabled
          ? '<i data-lucide="zap" class="w-3 h-3 inline mr-1"></i>Физика ВКЛ'
          : '<i data-lucide="zap-off" class="w-3 h-3 inline mr-1"></i>Физика ВЫКЛ';
      });
    }

    // Fit button
    const fitBtn = document.getElementById('graph-fit');
    if (fitBtn) {
      fitBtn.addEventListener('click', () => fitGraph());
    }

  } catch (err) {
    console.error('Graph load error:', err);
    if (loading) loading.classList.add('hidden');
    if (error) error.classList.remove('hidden');
    container.classList.remove('hidden');
    container.innerHTML = `
      <div class="flex items-center justify-center h-full">
        <div class="text-center">
          <p class="text-text-secondary mb-2">API недоступен</p>
          <p class="text-xs text-text-secondary">${err.message}</p>
          <p class="text-xs text-text-secondary mt-2">Убедитесь, что бэкенд запущен на ${API_BASE}</p>
        </div>
      </div>
    `;
  }
}

/**
 * Настроить обработчики вкладки "Граф связей".
 */
function setupGraphTabHandlers() {
  const loadBtn = document.getElementById('graph-load-btn');
  const innInput = document.getElementById('graph-inn-input');
  const websiteInput = document.getElementById('graph-website-input');

  if (loadBtn) {
    loadBtn.addEventListener('click', () => {
      const inn = innInput?.value?.trim();
      const website = websiteInput?.value?.trim() || null;
      if (!inn) {
        showNotification('Введите ИНН компании', 'error');
        return;
      }
      loadAndRenderGraph(inn, website);
    });
  }

  // Enter key in INN input
  if (innInput) {
    innInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        loadBtn?.click();
      }
    });
  }

  // Auto-load if INN is pre-filled
  const inn = innInput?.value?.trim();
  if (inn) {
    loadAndRenderGraph(inn);
  }
}

export function setupEventListeners(renderApp) {
  const roleStartupBtn = document.getElementById('role-startup');
  const roleFundBtn = document.getElementById('role-fund');
  const loginBtn = document.getElementById('login-btn');

  if (roleStartupBtn && roleFundBtn) {
    roleStartupBtn.addEventListener('click', () => {
      state.currentRole = 'startup';
      state.showAiConsentModal = false;
      renderApp();
    });
    roleFundBtn.addEventListener('click', () => {
      state.currentRole = 'fund';
      state.showAiConsentModal = false;
      renderApp();
    });
  }

  const aiConsentInfoBtn = document.getElementById('ai-consent-info-btn');
  if (aiConsentInfoBtn) {
    aiConsentInfoBtn.addEventListener('click', () => {
      state.showAiConsentModal = true;
      renderApp();
    });
  }

  const closeAiConsentModal = () => {
    state.showAiConsentModal = false;
    renderApp();
  };

  document.getElementById('ai-consent-modal-close-x')?.addEventListener('click', closeAiConsentModal);
  document.getElementById('ai-consent-modal-ok')?.addEventListener('click', closeAiConsentModal);

  const aiConsentOverlay = document.getElementById('ai-consent-modal-overlay');
  if (aiConsentOverlay) {
    aiConsentOverlay.addEventListener('click', (e) => {
      if (e.target === aiConsentOverlay) closeAiConsentModal();
    });
  }

  const consentCheckbox = document.getElementById('ai-registry-consent');
  const syncLoginButtonState = () => {
    const btn = document.getElementById('login-btn');
    if (!btn) return;
    if (state.currentRole !== 'startup') {
      btn.disabled = false;
      return;
    }
    const cb = document.getElementById('ai-registry-consent');
    btn.disabled = !cb?.checked;
  };
  syncLoginButtonState();
  if (consentCheckbox) {
    consentCheckbox.addEventListener('change', syncLoginButtonState);
  }

  if (loginBtn) {
    loginBtn.addEventListener('click', () => {
      const email = document.getElementById('login-email')?.value;
      const password = document.getElementById('login-password')?.value;
      if (email && password) {
        state.currentUser = { email };
        state.currentPage = state.currentRole;
        showNotification('Добро пожаловать в MacroMindAnalytics!', 'success');
        renderApp();
      } else {
        showNotification('Введите email и пароль', 'error');
      }
    });
  }

  const passwordField = document.getElementById('login-password');
  if (passwordField && loginBtn) {
    passwordField.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loginBtn.click();
    });
  }

  document.querySelectorAll('.upload-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const docId = btn.getAttribute('data-doc-id');
      if (docId && !state.uploadedDocuments.includes(docId)) {
        state.uploadedDocuments.push(docId);
        showNotification('Документ успешно загружен', 'success');
        renderApp();
      }
    });
  });

  const legalNo = document.getElementById('legal-entity-no');
  const legalYes = document.getElementById('legal-entity-yes');
  if (legalNo) {
    legalNo.addEventListener('click', () => {
      if (state.hasLegalEntity) {
        state.hasLegalEntity = false;
        state.uploadedDocuments = [];
        renderApp();
      }
    });
  }
  if (legalYes) {
    legalYes.addEventListener('click', () => {
      if (!state.hasLegalEntity) {
        state.hasLegalEntity = true;
        state.uploadedDocuments = [];
        renderApp();
      }
    });
  }

  const polygonStart = document.getElementById('polygon-start-btn');
  if (polygonStart) {
    polygonStart.addEventListener('click', () => {
      const industry = document.getElementById('startup-industry-select')?.value ?? '';
      const stage = document.getElementById('startup-stage-select')?.value ?? '';
      const site = document.getElementById('startup-site-select')?.value ?? '';
      const q = new URLSearchParams();
      if (industry) q.set('industry', industry);
      if (stage) q.set('stage', stage);
      if (site) q.set('site', site);
      q.set('autoStart', '1');
      window.location.href = `${window.location.origin}/kviz/index.html?${q.toString()}`;
    });
  }

  const pitchDeckUpload = document.getElementById('pitch-deck-upload');
  if (pitchDeckUpload) {
    pitchDeckUpload.addEventListener('click', () => {
      showNotification('Файл загружен и отправлен на анализ', 'success');
    });
  }

  const inviteLinkBtn = document.getElementById('invite-link-btn');
  if (inviteLinkBtn) {
    inviteLinkBtn.addEventListener('click', async () => {
      const u = new URL(window.location.href);
      u.search = '';
      u.hash = '';
      u.searchParams.set('startup', '1');
      try {
        await navigator.clipboard.writeText(u.toString());
        showNotification('Ссылка скопирована', 'success');
      } catch {
        showNotification('Не удалось скопировать ссылку', 'error');
      }
    });
  }

  document.querySelectorAll('.view-project-btn, .project-row').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      if (btn.classList.contains('project-row') && e.target.closest('button')) {
        return;
      }
      if (btn.classList.contains('project-row') && e.target.tagName !== 'BUTTON') {
        const projectId = btn.getAttribute('data-project-id');
        state.selectedProject = mockProjects.find((p) => p.id === projectId);
        state.activeTab = 'documents';
        state.currentPage = 'project';
        renderApp();
        // F28: рынок по привязке этой сделки
        if (state.selectedProject) {
          loadDealMarketSummary({
            inn: state.selectedProject.inn,
            projectId: state.selectedProject.id,
          }).then(() => {
            if (state.currentPage === 'project') renderApp();
          });
        }
      } else if (btn.classList.contains('view-project-btn')) {
        const row = btn.closest('tr');
        const projectId = row?.getAttribute('data-project-id');
        state.selectedProject = mockProjects.find((p) => p.id === projectId);
        state.activeTab = 'documents';
        state.currentPage = 'project';
        renderApp();
        if (state.selectedProject) {
          loadDealMarketSummary({
            inn: state.selectedProject.inn,
            projectId: state.selectedProject.id,
          }).then(() => {
            if (state.currentPage === 'project') renderApp();
          });
        }
      }
    });
  });

  const backToFund = document.getElementById('back-to-fund');
  if (backToFund) {
    backToFund.addEventListener('click', () => {
      state.currentPage = 'fund';
      state.selectedProject = null;
      renderApp();
    });
  }

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-tab');
      state.activeTab = tab;

      // Destroy previous graph if switching away
      if (tab !== 'graph') {
        destroyGraph();
      }

      document.querySelectorAll('.tab-btn').forEach((b) => {
        b.classList.remove('tab-active');
        b.classList.add('text-text-secondary');
      });
      btn.classList.add('tab-active');
      btn.classList.remove('text-text-secondary');
      renderApp();

      // Initialize graph if graph tab is selected
      if (tab === 'graph') {
        setupGraphTabHandlers();
      }
    });
  });

  const exportSummary = document.getElementById('export-summary');
  if (exportSummary) {
    exportSummary.addEventListener('click', async () => {
      const studyId = marketState.studyId;
      if (!studyId) {
        showNotification('Сначала создайте исследование рынка в блоке «Анализ рынка и конкурентов».', 'error');
        return;
      }
      try {
        const filename = await downloadMarketReport(studyId);
        showNotification(`Отчет сохранен: ${filename}`, 'success');
      } catch (err) {
        showNotification(err.message || 'Не удалось выгрузить отчет.', 'error');
      }
    });
  }

  const sendFeedbackBtn = document.getElementById('send-feedback');
  if (sendFeedbackBtn) {
    sendFeedbackBtn.addEventListener('click', () => {
      state.showFeedbackModal = true;
      renderApp();
    });
  }

  const cancelFeedback = document.getElementById('cancel-feedback');
  if (cancelFeedback) {
    cancelFeedback.addEventListener('click', () => {
      state.showFeedbackModal = false;
      renderApp();
    });
  }

  const sendFeedbackSubmit = document.getElementById('send-feedback-btn');
  if (sendFeedbackSubmit) {
    sendFeedbackSubmit.addEventListener('click', () => {
      const text = document.getElementById('feedback-text')?.value;
      if (text?.trim()) {
        state.showFeedbackModal = false;
        showNotification('Ответ отправлен стартапу', 'success');
        renderApp();
      } else {
        showNotification('Введите текст комментария', 'error');
      }
    });
  }

  const aiGenerate = document.getElementById('ai-generate');
  if (aiGenerate) {
    aiGenerate.addEventListener('click', () => {
      const textarea = document.getElementById('feedback-text');
      if (textarea) {
        textarea.value =
          'Благодарим за интерес к нашему фонду. Ваш проект показывает хороший потенциал, однако рекомендуем доработать финансовую модель и переоформить товарный знак на юридическое лицо. Будем рады рассмотреть обновлённые материалы.';
      }
    });
  }

  const switchRole = document.getElementById('switch-role');
  if (switchRole) {
    switchRole.addEventListener('click', () => {
      state.currentRole = state.currentRole === 'startup' ? 'fund' : 'startup';
      state.currentPage = state.currentRole;
      showNotification(`Переключено на роль: ${state.currentRole === 'startup' ? 'Стартап' : 'Фонд'}`, 'info');
      renderApp();
    });
  }

  const logout = document.getElementById('logout');
  if (logout) {
    logout.addEventListener('click', () => {
      state.currentPage = 'login';
      state.currentUser = null;
      renderApp();
    });
  }

  // Переключатель секции фонда (Воронка / Портфель / Слабые сигналы / Архив)
  document.querySelectorAll('.fund-phase-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const phase = btn.getAttribute('data-phase');
      if (phase && phase !== state.fundPhase) {
        state.fundPhase = phase;
        state.currentFundTab = 'projects';
        state.currentPostTab = 'portfolio';
        renderApp();
      }
    });
  });

  // Навигация фонда (фаза "до инвестиции")
  document.querySelectorAll('.fund-nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-tab');
      if (tab) {
        state.currentFundTab = tab;
        renderApp();
      }
    });
  });

  // Навигация фонда (фаза "после инвестиции")
  document.querySelectorAll('.post-nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-post-tab');
      if (tab) {
        state.currentPostTab = tab;
        renderApp();
      }
    });
  });

  // Клик по карточке портфельной компании → открыть модал
  document.querySelectorAll('.company-card').forEach((card) => {
    card.addEventListener('click', () => {
      const companyId = card.getAttribute('data-company-id');
      const company = portfolioCompanies.find(c => c.id === companyId);
      if (company) {
        state.selectedCompany = company;
        state.companyModalTab = 'overview';
        renderApp();
      }
    });
  });

  // Модал компании — закрытие
  const closeModal = () => {
    state.selectedCompany = null;
    renderApp();
  };
  document.getElementById('company-modal-close')?.addEventListener('click', closeModal);
  document.getElementById('company-modal-overlay')?.addEventListener('click', (e) => {
    if (e.target === document.getElementById('company-modal-overlay')) closeModal();
  });

  // Модал компании — переключение вкладок
  document.querySelectorAll('.company-modal-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-modal-tab');
      if (tab && tab !== state.companyModalTab) {
        state.companyModalTab = tab;
        renderApp();
      }
    });
  });

  // VentureBot — быстрые команды
  document.querySelectorAll('.chat-quick-cmd').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (input) {
        input.value = btn.textContent.trim();
        input.focus();
      }
    });
  });

  // VentureBot — отправка сообщения
  const chatSend = document.getElementById('chat-send-btn');
  if (chatSend) {
    chatSend.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (!input?.value?.trim()) return;
      const messages = document.getElementById('chat-messages');
      if (messages) {
        const userMsg = document.createElement('div');
        userMsg.className = 'flex gap-3 flex-row-reverse fade-in';
        userMsg.innerHTML = `
          <div class="w-9 h-9 bg-[#444] rounded-full flex-shrink-0 flex items-center justify-center text-text-secondary">
            <span class="text-xs font-bold">ЮО</span>
          </div>
          <div class="bg-primary text-white p-4 rounded-2xl rounded-tr-none max-w-2xl">
            <p class="text-sm leading-relaxed">${input.value.trim()}</p>
          </div>
        `;
        messages.appendChild(userMsg);
        messages.scrollTop = messages.scrollHeight;
        input.value = '';
      }
    });
  }

  // Initialize graph if graph tab is already active
  if (state.activeTab === 'graph') {
    setupGraphTabHandlers();
  }

  // Обработчик формы проверки юрлица
  const checkCompanyForm = document.getElementById('check-company-form');
  if (checkCompanyForm) {
    checkCompanyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameOrInn = document.getElementById('company-name-inn')?.value?.trim();
      const searchQuery = document.getElementById('company-search-query')?.value?.trim();
      const searchType = document.getElementById('company-search-type')?.value || 'auto';

      // Приоритет: ИНН → точная проверка. Иначе — поиск по свободному запросу.
      if (nameOrInn && /^\d{10}$|^\d{12}$/.test(nameOrInn)) {
        if (state.checkHistory?.some(record => record.inn === nameOrInn && record.status === 'Проверяется')) {
          showNotification('Проверка этого ИНН уже выполняется.', 'error');
          return;
        }
        checkCompanyForm.reset();
        await runCompanyCheckByNameOrInn(nameOrInn, null);
        return;
      }

      if (nameOrInn && !/^\d+$/.test(nameOrInn)) {
        // пользователь ввёл текст в поле ИНН — тоже ищем
        checkCompanyForm.reset();
        await runCompanySearch(nameOrInn, { page: 1, searchTypeOverride: searchType });
        return;
      }

      if (searchQuery) {
        checkCompanyForm.reset();
        await runCompanySearch(searchQuery, { page: 1, searchTypeOverride: searchType });
        return;
      }

      showNotification('Укажите ИНН (10 или 12 цифр) или поисковый запрос.', 'error');
    });
  }

  async function runCompanySearch(query, { page = 1, searchTypeOverride = null } = {}) {
    const token = (state.companySearchToken || 0) + 1;
    state.companySearchToken = token;
    state.companySearchLoading = true;
    state.companySearchError = null;
    state.companySearchEmpty = false;
    // keep previous results while loading page 2+, so a failure doesn't wipe page 1
    if (page === 1) {
      state.companySearchResults = null;
    }
    state.companySearchQueryLabel = query;
    state.companySearchPage = page;
    renderApp();
    try {
      const data = await searchCompanies(query, {
        apiBase: API_BASE,
        page,
        searchTypeOverride: searchTypeOverride === 'auto' ? null : searchTypeOverride,
      });
      // Ignore stale responses from an older search (MIMO rules §9).
      if (state.companySearchToken !== token) return;
      state.companySearchResults = data.results;
      state.companySearchTotalPages = data.totalPages;
      state.companySearchPage = data.page || page;
      state.companySearchLastParams = {
        query,
        searchTypeOverride: searchTypeOverride === 'auto' ? null : searchTypeOverride,
      };
      state.companySearchEmpty = !data.results.length;
      state.companySearchError = null;
    } catch (err) {
      if (state.companySearchToken !== token) return;
      // Keep already shown results on page navigation failure.
      if (page > 1 && state.companySearchResults?.length) {
        showNotification(err.message || 'Не удалось загрузить следующую страницу.', 'error');
      } else {
        state.companySearchResults = null;
        state.companySearchEmpty = false;
        state.companySearchError = err.message || 'Не удалось выполнить поиск.';
        showNotification(state.companySearchError, 'error');
      }
    }
    if (state.companySearchToken === token) {
      state.companySearchLoading = false;
    }
    if (state.currentPage === 'fund' && state.currentFundTab !== 'check-person') {
      renderApp();
      document.getElementById('company-search-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  async function runCompanyCheckByNameOrInn(inn, url) {
    const newRecord = {
      id: `check-${Date.now()}`,
      name: inn,
      inn,
      url: url || null,
      requestedAt: new Date().toISOString().split('T')[0],
      status: 'Проверяется',
      findings: null,
      riskLevel: null,
      personResults: [],
      finances: null,
      financesError: null,
      timeline: null,
      timelineError: null,
    };

    if (!state.checkHistory) state.checkHistory = [];
    state.checkHistory.unshift(newRecord);
    persistFromAppState(state);

    // Все модули сразу, каждый со своим кружком в шапке
    const moduleLoading = {
      company: true,
      finances: /^\d{10}$/.test(inn),
      timeline: true,
      market: true,
      persons: true,
    };
    REGISTRY_SECTIONS.forEach((s) => { moduleLoading[`reg_${s.key}`] = true; });
    state.moduleLoading = moduleLoading;
    state.checkLoading = true;
    state.checkError = null;
    state.selectedCheckResult = newRecord;
    state.personAutoLoadingCount = 0;
    state.personResultsExpanded = true;
    state.companyFinances = null;
    state.companyFinancesError = null;
    state.companyTimeline = null;
    state.companyTimelineError = null;
    state.timelineExpanded = false;
    state.companyRegistries = {};
    state.registryExpanded = {};
    resetMarketState();
    renderApp();

    const onCompanyTab = () => state.currentPage === 'fund' && state.currentFundTab !== 'check-person';
    const CHECK_TIMEOUT_MS = 120000;
    const startedAt = Date.now();
    const timeLeft = () => Math.max(1000, CHECK_TIMEOUT_MS - (Date.now() - startedAt));
    const r = () => { if (onCompanyTab()) renderApp(); };

    try {
      // Checko: компания, финансы, история, реестры — ВСЕ модули, до анализа рынка
      const checkoBudget = Math.min(60000, timeLeft());
      const [companyRes, finRes, tlRes, registryResults] = await Promise.all([
        completeCompanyCheck(newRecord, { apiBase: API_BASE, timeoutMs: Math.min(35000, checkoBudget) })
          .then((rec) => {
            moduleLoading.company = false;
            r();
            return rec;
          }),
        /^\d{10}$/.test(inn)
          ? (async () => {
              // retry once on Checko timeout — финансы критичны для рыночного блока
              let res = await fetchCompanyFinances(inn, { apiBase: API_BASE, timeoutMs: checkoBudget });
              if (res && res.status === 'error' && /не ответил вовремя|timeout/i.test(res.message || '')) {
                moduleLoading.finances = 'retry';
                r();
                await new Promise((r2) => setTimeout(r2, 1500));
                res = await fetchCompanyFinances(inn, { apiBase: API_BASE, timeoutMs: checkoBudget });
              }
              moduleLoading.finances = false;
              r();
              return res;
            })()
          : Promise.resolve(null),
        fetchCompanyTimeline(inn, { apiBase: API_BASE, timeoutMs: Math.min(35000, checkoBudget) })
          .then((res) => { moduleLoading.timeline = false; r(); return res; }),
        Promise.all(REGISTRY_SECTIONS.map(async (section) => {
          const result = section.method === 'contracts'
            ? await fetchContractsRegistry(inn, { apiBase: API_BASE, timeoutMs: Math.min(35000, checkoBudget) })
            : await fetchCompanyRegistry(section.method, inn, { apiBase: API_BASE, timeoutMs: Math.min(35000, checkoBudget) });
          moduleLoading[`reg_${section.key}`] = false;
          state.companyRegistries = {
            ...state.companyRegistries,
            [section.key]: result.status === 'ok' || result.status === 'empty'
              ? { items: result.registry?.items || [], partialError: result.partialError || null }
              : null,
            [`${section.key}_error`]: result.status === 'error' ? result.message : (result.registry ? null : result.message),
          };
          r();
          return { section, result };
        })),
      ]);

      if (finRes) {
        if (finRes.status === 'ok' || finRes.status === 'empty') {
          newRecord.finances = finRes.finances;
          newRecord.financesError = finRes.status === 'empty' ? finRes.message : null;
        } else {
          newRecord.finances = null;
          newRecord.financesError = finRes.message;
        }
      }
      if (tlRes.status === 'ok' || tlRes.status === 'empty') {
        newRecord.timeline = tlRes.timeline;
        newRecord.timelineError = tlRes.status === 'empty' ? tlRes.message : null;
      } else {
        newRecord.timeline = null;
        newRecord.timelineError = tlRes.message;
      }
      newRecord.registries = newRecord.registries || {};
      for (const { section, result } of registryResults) {
        const payload = result.status === 'ok' || result.status === 'empty' ? result.registry : null;
        newRecord.registries[section.key] = {
          data: payload,
          error: result.status === 'error' ? result.message : (result.partialError || null),
        };
      }

      // Физлица — после компании (нужны ИНН руководителей)
      if (newRecord.status === 'Анализ завершен' && newRecord.company) {
        const people = extractPersonInns(newRecord.company);
        if (people.length) {
          newRecord.personResults = people;
          const batch = selectAutoBatch(people, MAX_AUTO_PERSON_CHECKS);
          if (batch.length) {
            batch.forEach(p => { p.checkStatus = 'checking'; });
            r();
            const personCompleted = await checkPersonsFromCompany(batch, {
              apiBase: API_BASE,
              timeoutMs: Math.min(35000, timeLeft()),
            });
            const byInn = new Map(personCompleted.map(x => [x.inn, x]));
            for (const p of people) {
              const done = p.inn ? byInn.get(p.inn) : null;
              if (done) {
                p.checkStatus = done.status === 'Анализ завершен' ? 'done' : 'error';
                p.person = done.person || null;
                p.findings = done.findings;
                p.requestedAt = done.requestedAt;
              }
            }
          }
        }
      }
      moduleLoading.persons = false;
      r();

      // Рынок — ТОЛЬКО после того, как Checko полностью ответил
      // (компания + финансы + история + реестры). Не раньше.
      const checkoReady = Boolean(newRecord.company)
        && finRes !== undefined
        && tlRes !== undefined
        && Array.isArray(registryResults);
      moduleLoading.market = 'waiting_checko';
      r();
      if (checkoReady && newRecord.company) {
        const marketTask = runAutoMarketAnalysis({
          company: newRecord.company,
          finances: newRecord.finances,
          registries: Object.fromEntries(
            REGISTRY_SECTIONS.map(s => [s.key, newRecord.registries?.[s.key]?.data || null]),
          ),
        });
        r();
        await marketTask;
      }
      moduleLoading.market = false;

      if (newRecord.status === 'Анализ завершен' && newRecord.company) {
        state.checkError = null;
      } else {
        state.checkError = newRecord.findings || 'Не удалось завершить проверку.';
      }
    } catch (err) {
      state.checkError = err?.message || 'Не удалось завершить проверку. Повторите попытку.';
      newRecord.status = 'Ошибка проверки';
      newRecord.findings = state.checkError;
    } finally {
      state.checkLoading = false;
      state.moduleLoading = {};
      state.selectedCheckResult = newRecord;
      state.companyFinances = newRecord.finances || null;
      state.companyFinancesError = newRecord.financesError || null;
      state.companyTimeline = newRecord.timeline || null;
      state.companyTimelineError = newRecord.timelineError || null;
      state.personAutoLoadingCount = 0;
      const restored = {};
      for (const section of REGISTRY_SECTIONS) {
        const saved = newRecord.registries?.[section.key];
        restored[section.key] = saved?.data
          ? { items: saved.data.items || [], partialError: saved.error || null }
          : null;
        if (saved?.error && !saved.data) {
          restored[`${section.key}_error`] = saved.error;
        }
      }
      state.companyRegistries = restored;
      state.registriesLoading = false;
      state.moduleLoading = {};
      persistFromAppState(state);
      if (onCompanyTab()) renderApp();
    }
  }

  // «Проверить остальных» / повтор ошибки по ИНН в текущей карточке компании
  document.getElementById('person-check-rest')?.addEventListener('click', async () => {
    const record = state.selectedCheckResult;
    const people = record?.personResults || [];
    const batch = selectAutoBatch(people, MAX_AUTO_PERSON_CHECKS);
    if (!record || !batch.length) return;
    batch.forEach(p => { p.checkStatus = 'checking'; });
    state.personAutoLoadingCount = batch.length;
    state.personResultsExpanded = true;
    renderApp();
    const completed = await checkPersonsFromCompany(batch, { apiBase: API_BASE });
    state.personAutoLoadingCount = 0;
    const byInn = new Map(completed.map(r => [r.inn, r]));
    for (const p of people) {
      const done = p.inn ? byInn.get(p.inn) : null;
      if (done) {
        p.checkStatus = done.status === 'Анализ завершен' ? 'done' : 'error';
        p.person = done.person || null;
        p.findings = done.findings;
      }
    }
    if (state.selectedCheckResult?.id === record.id) state.selectedCheckResult = record;
    renderApp();
  });

  document.querySelectorAll('.person-retry-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const inn = btn.getAttribute('data-inn');
      const record = state.selectedCheckResult;
      const person = (record?.personResults || []).find(p => p.inn === inn);
      if (!person) return;
      person.checkStatus = 'checking';
      state.personAutoLoadingCount = 1;
      renderApp();
      const [done] = await checkPersonsFromCompany([person], { apiBase: API_BASE });
      state.personAutoLoadingCount = 0;
      person.checkStatus = done.status === 'Анализ завершен' ? 'done' : 'error';
      person.person = done.person || null;
      person.findings = done.findings;
      renderApp();
    });
  });

  // Выбор организации из результатов поиска → проверка по ИНН
  document.querySelectorAll('.company-search-item').forEach((item) => {
    item.addEventListener('click', () => {
      const inn = item.getAttribute('data-inn');
      if (!inn || !/^\d{10}$|^\d{12}$/.test(inn)) {
        showNotification('У этой записи нет ИНН для проверки.', 'error');
        return;
      }
      if (state.checkHistory?.some(r => r.inn === inn && r.status === 'Проверяется')) {
        showNotification('Проверка этого ИНН уже выполняется.', 'error');
        return;
      }
      state.companySearchResults = null;
      runCompanyCheckByNameOrInn(inn, null);
    });
  });

  document.getElementById('company-search-clear')?.addEventListener('click', () => {
    state.companySearchResults = null;
    state.companySearchError = null;
    state.companySearchEmpty = false;
    state.companySearchTotalPages = null;
    state.companySearchPage = 1;
    renderApp();
  });

  document.getElementById('company-search-prev')?.addEventListener('click', () => {
    const params = state.companySearchLastParams;
    if (!params || state.companySearchPage <= 1) return;
    runCompanySearch(params.query, {
      page: state.companySearchPage - 1,
      searchTypeOverride: params.searchTypeOverride,
    });
  });

  document.getElementById('company-search-next')?.addEventListener('click', () => {
    const params = state.companySearchLastParams;
    if (!params) return;
    if (state.companySearchTotalPages && state.companySearchPage >= state.companySearchTotalPages) return;
    runCompanySearch(params.query, {
      page: state.companySearchPage + 1,
      searchTypeOverride: params.searchTypeOverride,
    });
  });

  // Клик по записи истории юрлиц — показать компанию и связанных физлиц
  document.querySelectorAll('.check-history-item').forEach((item) => {
    item.addEventListener('click', () => {
      const checkId = item.getAttribute('data-check-id');
      const record = state.checkHistory?.find(r => r.id === checkId);
      if (record?.company) {
        state.selectedCheckResult = record;
        state.checkError = null;
        state.checkLoading = false;
        state.personAutoLoadingCount = 0;
        state.personResultsExpanded = (record.personResults || []).length > 0;
        state.companyFinances = record.finances || null;
        state.companyFinancesError = record.financesError || null;
        state.companyFinancesLoading = false;
        state.companyTimeline = record.timeline || null;
        state.companyTimelineError = record.timelineError || null;
        state.companyTimelineLoading = false;
        state.timelineExpanded = false;
        state.registryExpanded = {};
        const restored = {};
        for (const section of REGISTRY_SECTIONS) {
          const saved = record.registries?.[section.key];
          restored[section.key] = saved?.data
            ? { items: saved.data.items || [], partialError: saved.error || null }
            : null;
          if (saved?.error && !saved.data) {
            restored[`${section.key}_error`] = saved.error;
          }
        }
        state.companyRegistries = restored;
        state.registriesLoading = false;
        persistFromAppState(state);
        renderApp();
        document.getElementById('check-result-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // не оставлять рыночный вывод предыдущей компании (plan §4.1)
        resetMarketState();
        if (record.company) {
          runAutoMarketAnalysis({
            company: record.company,
            finances: record.finances,
            registries: Object.fromEntries(
              REGISTRY_SECTIONS.map(s => [s.key, record.registries?.[s.key]?.data || null]),
            ),
          }).then(() => {
            if (state.currentPage === 'fund') renderApp();
          });
          renderApp();
        }
      }
    });
  });

  // Форма ручной проверки физлица (вкладка «Проверить физ. лицо»)
  const personCheckForm = document.getElementById('person-check-form');
  if (personCheckForm) {
    personCheckForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const inn = document.getElementById('person-inn')?.value?.trim();

      if (!/^\d{12}$/.test(inn || '')) {
        showNotification('Укажите ИНН физического лица: 12 цифр.', 'error');
        return;
      }
      if (state.personCheckHistory?.some(r => r.inn === inn && r.status === 'Проверяется')) {
        showNotification('Проверка этого ИНН уже выполняется.', 'error');
        return;
      }

      const newRecord = {
        id: `person-${Date.now()}`,
        name: inn,
        inn,
        auto: false,
        requestedAt: new Date().toISOString().split('T')[0],
        status: 'Проверяется',
        findings: null,
        riskLevel: null,
      };

      if (!state.personCheckHistory) {
        state.personCheckHistory = [];
      }
      state.personCheckHistory.unshift(newRecord);
      persistFromAppState(state);

      personCheckForm.reset();
      state.personCheckLoading = true;
      state.personCheckError = null;
      state.selectedPersonResult = newRecord;
      renderApp();

      await completePersonCheck(newRecord, { apiBase: API_BASE });
      state.personCheckLoading = false;
      if (newRecord.status === 'Анализ завершен' && newRecord.person) {
        state.selectedPersonResult = newRecord;
        state.personCheckError = null;
      } else {
        state.selectedPersonResult = newRecord;
        state.personCheckError = newRecord.findings || 'Не удалось завершить проверку.';
      }
      persistFromAppState(state);
      if (state.currentPage === 'fund' && state.currentFundTab === 'check-person') {
        renderApp();
        document.getElementById(`person-result-card-${inn}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  // Клик по истории физлиц
  document.querySelectorAll('.person-history-item').forEach((item) => {
    item.addEventListener('click', () => {
      const personId = item.getAttribute('data-person-id');
      const record = state.personCheckHistory?.find(r => r.id === personId);
      if (record?.person) {
        state.selectedPersonResult = record;
        state.personCheckError = null;
        state.personCheckLoading = false;
        persistFromAppState(state);
        renderApp();
        document.getElementById(`person-result-card-${record.inn}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  document.getElementById('timeline-toggle')?.addEventListener('click', () => {
    state.timelineExpanded = !state.timelineExpanded;
    renderApp();
    if (!state.timelineExpanded) {
      document.getElementById('timeline-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

  // Модуль «Анализ рынка и конкурентов»
  setupMarketListeners(renderApp, {
    getInn: () => state.selectedCheckResult?.company?.inn,
    getCompanyName: () => state.selectedCheckResult?.company?.name,
  });

  document.querySelectorAll('.registry-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-expand-key');
      if (!key) return;
      state.registryExpanded = {
        ...(state.registryExpanded || {}),
        [key]: !state.registryExpanded?.[key],
      };
      renderApp();
    });
  });

  // ============================================================
  // Поиск слабых сигналов
  // ============================================================
  const PROGRESS_STEPS = [
    { id: 'queued', title: 'В очереди', count: 'анализ поставлен' },
    { id: 'corpus', title: 'Сбор корпуса', count: '12 480 работ' },
    { id: 'candidates', title: 'Извлечение кандидатов', count: '186 тем' },
    { id: 'score', title: 'Признаки и индекс', count: '15 в топе' },
    { id: 'cards', title: 'Карточки и доказательства', count: '15 / 15' },
  ];

  async function runWeakSignalsSearch(rawQuery) {
    const query = (rawQuery || '').trim();
    if (query.length < 3) {
      state.weakSignalsError = 'Введите направление, не короче трёх символов.';
      renderApp();
      return;
    }
    state.weakSignalsError = '';
    state.weakSignalsQuery = query;
    state.weakSignalsSelectedId = null;
    state.weakSignalsView = 'results';
    state.weakSignalsPhase = 'progress';
    state.weakSignalsProgress = { done: 1, steps: PROGRESS_STEPS };
    renderApp();

    // One render per step; keep animation short so the tab does not "blink" forever.
    for (let n = 2; n <= PROGRESS_STEPS.length; n += 1) {
      // eslint-disable-next-line no-await-in-loop
      await new Promise(resolve => setTimeout(resolve, 280));
      state.weakSignalsProgress = { done: n, steps: PROGRESS_STEPS };
      if (state.fundPhase === 'weak-signals' && state.currentPage === 'fund') renderApp();
    }
    state.weakSignalsPhase = 'done';
    if (state.currentPage === 'fund' && state.fundPhase === 'weak-signals') {
      renderApp();
      document.getElementById('weak-signals-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  async function loadKnowledgeSignals({ force = false } = {}) {
    // Astra/UI: avoid reload loop on every renderApp (flicker + hang).
    if (state.knowledgeSignalsLoading) return;
    if (state.knowledgeSignalsLoaded && !force) return;
    state.knowledgeSignalsLoading = true;
    state.knowledgeSignalsError = '';
    if (state.currentPage === 'fund' && state.fundPhase === 'weak-signals') renderApp();
    try {
      const mod = await import('./api/knowledge.js');
      const data = await mod.listKnowledgeSignals({});
      state.knowledgeSignals = {
        events: data?.events || [],
        hypotheses: data?.hypotheses || [],
      };
      state.knowledgeSignalsLoaded = true;
    } catch (err) {
      state.knowledgeSignalsError = err?.message
        || 'База знаний недоступна. Проверьте KNOWLEDGE_DATABASE_URL и /api/v1/knowledge.';
      state.knowledgeSignals = { events: [], hypotheses: [] };
      state.knowledgeSignalsLoaded = true; // do not hammer the API on re-render
    } finally {
      state.knowledgeSignalsLoading = false;
      if (state.currentPage === 'fund' && state.fundPhase === 'weak-signals') renderApp();
    }
  }

  if (document.getElementById('weak-signals-form')) {
    loadKnowledgeSignals();
  }

  const weakForm = document.getElementById('weak-signals-form');
  if (weakForm) {
    weakForm.addEventListener('submit', (e) => {
      e.preventDefault();
      runWeakSignalsSearch(document.getElementById('weak-signals-query')?.value);
    });
    document.getElementById('weak-signals-query')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runWeakSignalsSearch(document.getElementById('weak-signals-query')?.value);
      }
    });
  }

  document.querySelectorAll('.weak-signal-chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      runWeakSignalsSearch(btn.getAttribute('data-query'));
    });
  });

  document.querySelectorAll('.weak-signals-view-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.getAttribute('data-view');
      if (view && view !== state.weakSignalsView) {
        state.weakSignalsView = view;
        state.weakSignalsSelectedId = null;
        renderApp();
      }
    });
  });

  document.querySelectorAll('.weak-signal-card').forEach((card) => {
    card.addEventListener('click', () => {
      const trendId = card.getAttribute('data-trend-id');
      if (trendId) {
        state.weakSignalsSelectedId = trendId;
        renderApp();
        document.getElementById('weak-signal-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  document.getElementById('weak-signal-back')?.addEventListener('click', () => {
    state.weakSignalsSelectedId = null;
    renderApp();
    document.getElementById('weak-signals-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  // ============================================================
  // Обработчик формы «Компетенции»
  // ============================================================
  const compForm = document.getElementById('competency-search-form');
  if (compForm) {
    compForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const fullName = document.getElementById('comp-full-name')?.value?.trim();
      const nicknames = document.getElementById('comp-nicknames')?.value?.trim();
      const position = document.getElementById('comp-position')?.value?.trim();
      const company = document.getElementById('comp-company')?.value?.trim();
      const city = document.getElementById('comp-city')?.value?.trim();
      const skills = document.getElementById('comp-skills')?.value?.trim();

      if (!fullName) {
        showNotification('Укажите ФИО', 'error');
        return;
      }

      // Проверяем что есть хотя бы одно доп. поле
      if (!nicknames && !position && !company && !city && !skills) {
        showNotification('Добавьте хотя бы одно дополнительное поле для сужения поиска', 'error');
        return;
      }

      const resultDiv = document.getElementById('competency-result');
      if (resultDiv) {
        resultDiv.innerHTML = `
          <div class="bg-card rounded-2xl shadow-soft p-8 text-center">
            <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
            <p class="text-text-secondary">Ищем кандидатов...</p>
          </div>
        `;
      }

      try {
        const nicknamesList = nicknames ? nicknames.split(',').map(s => s.trim()).filter(Boolean) : null;
        const body = {
          full_name: fullName,
          nicknames: nicknamesList,
          position: position || null,
          company: company || null,
          city: city || null,
          skills: skills ? skills.split(',').map(s => s.trim()).filter(Boolean) : null,
        };

        const response = await fetch(`${PEOPLE_API_BASE}/api/v1/people/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (resultDiv) {
          resultDiv.innerHTML = renderCandidates(data.candidates, body);
          createIcons({ icons });

          // Обработчики кликов по кандидатам
          document.querySelectorAll('.competency-candidate').forEach(card => {
            card.addEventListener('click', async () => {
              const candidateFullName = card.getAttribute('data-full-name');
              const candidateCompany = card.getAttribute('data-company');
              const candidatePosition = card.getAttribute('data-position');
              const candidateCity = card.getAttribute('data-city');
              let candidateAccounts = {};
              try {
                candidateAccounts = JSON.parse(card.getAttribute('data-accounts') || '{}');
              } catch {
                candidateAccounts = {};
              }

              // Показываем загрузку
              resultDiv.innerHTML = `
                <div class="bg-card rounded-2xl shadow-soft p-8 text-center">
                  <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
                  <p class="text-text-secondary">Загружаем профиль ${candidateFullName}...</p>
                </div>
              `;

              try {
                const profileResponse = await fetch(`${PEOPLE_API_BASE}/api/v1/people/profile`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    full_name: candidateFullName,
                    selected_accounts: candidateAccounts,
                    nicknames: nicknamesList,
                    company: candidateCompany || null,
                    position: candidatePosition || null,
                    city: candidateCity || null,
                  }),
                });

                if (!profileResponse.ok) {
                  throw new Error(`HTTP ${profileResponse.status}`);
                }

                const profile = await profileResponse.json();

                resultDiv.innerHTML = renderProfileReport(profile);
                createIcons({ icons });

                // Обработчик PDF экспорта
                const pdfBtn = document.getElementById('export-pdf-btn');
                if (pdfBtn) {
                  pdfBtn.addEventListener('click', () => {
                    showNotification('PDF экспорт в разработке', 'info');
                  });
                }

                // Сохраняем в историю
                if (!state.competencyHistory) {
                  state.competencyHistory = [];
                }
                state.competencyHistory.unshift({
                  full_name: candidateFullName,
                  company: candidateCompany || null,
                  score: profile.competence_score,
                  date: new Date().toISOString().split('T')[0],
                });

              } catch (err) {
                resultDiv.innerHTML = `
                  <div class="bg-card rounded-2xl shadow-soft p-8 text-center">
                    <i data-lucide="alert-circle" class="w-12 h-12 text-red-400 mx-auto mb-4"></i>
                    <h3 class="text-lg font-semibold text-text-main mb-2">Ошибка загрузки профиля</h3>
                    <p class="text-text-secondary">${err.message}</p>
                  </div>
                `;
                createIcons({ icons });
              }
            });
          });
        }

      } catch (err) {
        if (resultDiv) {
          resultDiv.innerHTML = `
            <div class="bg-card rounded-2xl shadow-soft p-8 text-center">
              <i data-lucide="alert-circle" class="w-12 h-12 text-red-400 mx-auto mb-4"></i>
              <h3 class="text-lg font-semibold text-text-main mb-2">Ошибка поиска</h3>
              <p class="text-text-secondary">${err.message}</p>
              <p class="text-xs text-text-secondary mt-2">Убедитесь что сервер запущен на ${PEOPLE_API_BASE}</p>
            </div>
          `;
          createIcons({ icons });
        }
      }
    });
  }
}
