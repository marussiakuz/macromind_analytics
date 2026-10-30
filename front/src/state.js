import { hydrateAppState } from './checkHistoryStore.js';

export const state = {
  currentPage: 'login',
  currentRole: 'startup',
  currentUser: null,
  selectedProject: null,
  activeTab: 'documents',
  notifications: [],
  uploadedDocuments: [],
  hasLegalEntity: false,
  showFeedbackModal: false,
  feedbackText: '',
  showAiConsentModal: false,
  /** Активная вкладка в панели фонда (фаза "до"): 'projects' | 'check-company' (Поиск) */
  currentFundTab: 'projects',
  /** История проверенных компаний (с personResults) */
  checkHistory: [],
  /** Активная проверка юрлица (карточка + физлица) */
  selectedCheckResult: null,
  /** Идёт запрос к API проверки компании */
  checkLoading: false,
  /** Текст ошибки последней проверки компании */
  checkError: null,
  /** История ручных проверок физлиц */
  personCheckHistory: [],
  /** Активная проверка физлица (ручной поиск) */
  selectedPersonResult: null,
  /** Идёт запрос person API */
  personCheckLoading: false,
  /** Сколько автопроверок физлиц выполняется */
  personAutoLoadingCount: 0,
  /** Блок «Деловые связи физлиц» раскрыт */
  personResultsExpanded: true,
  /** Ошибка последней ручной проверки физлица */
  personCheckError: null,
  /** Финансовая отчетность текущей проверки компании */
  companyFinances: null,
  companyFinancesLoading: false,
  companyFinancesError: null,
  /** История событий (timeline.md) */
  companyTimeline: null,
  companyTimelineLoading: false,
  companyTimelineError: null,
  timelineExpanded: false,
  /** Реестры (арбитраж, ФССП, госзакупки, Федресурс, ЕФРСБ, проверки) */
  companyRegistries: {},
  registryExpanded: {},
  registriesLoading: false,
  /** Параллельная загрузка модулей проверки */
  moduleLoading: {},
  /** Секция фонда: 'funnel' | 'portfolio' | 'archive' */
  fundPhase: 'funnel',
  /** Активная вкладка в секции «Портфель»: 'portfolio' | 'companies' | 'obligations' | 'assistant' */
  currentPostTab: 'portfolio',
  /** Выбранная портфельная компания */
  selectedCompany: null,
  /** Активная вкладка в модале компании */
  companyModalTab: 'overview',
  /** История поисков компетенций */
  competencyHistory: [],
  /** Поиск слабых сигналов: idle | progress | done */
  weakSignalsPhase: 'idle',
  weakSignalsQuery: '',
  weakSignalsError: '',
  weakSignalsView: 'results',
  weakSignalsSelectedId: null,
  weakSignalsProgress: null,
  /** Сигналы базы знаний (knowledge API): { events, hypotheses } */
  knowledgeSignals: null,
  knowledgeSignalsLoading: false,
  knowledgeSignalsLoaded: false,
  knowledgeSignalsError: '',
  /** Результаты поиска компаний (search.md) */
  companySearchResults: null,
  companySearchLoading: false,
  companySearchError: null,
  companySearchEmpty: false,
  companySearchQueryLabel: '',
  companySearchPage: 1,
  companySearchTotalPages: null,
  companySearchLastParams: null,
  companySearchToken: 0,
};

// История оценки переживает reload страницы (localStorage).
hydrateAppState(state);
