/** UI-состояние модуля «Рынок и конкуренты» (plan §16). */

export const marketState = {
  /** Открыт ли подробный экран исследования */
  detailOpen: false,
  /** id активного исследования */
  studyId: null,
  study: null,
  loading: false,
  progress: null,
  error: null,
  /** последние расчёты */
  topDown: null,
  bottomUp: null,
  triangulation: null,
  observations: [],
  competitors: [],
  /** MDS */
  mds: null,
  mdsError: null,
  /** Delphi */
  delphiRoundId: null,
  delphiSummary: null,
  delphiError: null,
  /** сводка для блока на проверке юрлица */
  summary: null,
  /** F28: сводка привязанной сделки (отдельная от проверки компании) */
  dealSummary: null,
  dealLoading: false,
  dealError: null,
  /** привязки к ИНН/проекту */
  bindings: [],
  /** Knowledge search (Task2 §8/§12) */
  knowledgeQuery: '',
  knowledgeResult: null,
  knowledgeLoading: false,
  knowledgeError: null,
};

export function resetMarketState() {
  marketState.detailOpen = false;
  marketState.studyId = null;
  marketState.study = null;
  marketState.loading = false;
  marketState.progress = null;
  marketState.error = null;
  marketState.topDown = null;
  marketState.bottomUp = null;
  marketState.triangulation = null;
  marketState.observations = [];
  marketState.competitors = [];
  marketState.mds = null;
  marketState.mdsError = null;
  marketState.delphiRoundId = null;
  marketState.delphiSummary = null;
  marketState.delphiError = null;
  marketState.summary = null;
  marketState.dealSummary = null;
  marketState.dealLoading = false;
  marketState.dealError = null;
  marketState.bindings = [];
  marketState.knowledgeQuery = '';
  marketState.knowledgeResult = null;
  marketState.knowledgeLoading = false;
  marketState.knowledgeError = null;
}
