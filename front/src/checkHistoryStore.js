/**
 * Persist «История оценки» across page reloads (localStorage).
 * Keeps a bounded number of check records; oversized payloads are trimmed.
 */

const STORAGE_KEY = 'mma_check_history_v1';
const MAX_CHECKS = 25;
const MAX_PERSON_CHECKS = 25;
/** Rough localStorage budget per write (chars). */
const MAX_PAYLOAD_CHARS = 3_500_000;

function storage() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

function trimRecord(record) {
  if (!record || typeof record !== 'object') return record;
  const copy = { ...record };
  // Drop bulky raw HTML if present; UI rebuilds report from JSON summary.
  if (typeof copy.report_html === 'string' && copy.report_html.length > 2000) {
    copy.report_html = '';
  }
  if (copy.marketSummary?.report_html) {
    copy.marketSummary = { ...copy.marketSummary, report_html: '' };
  }
  return copy;
}

export function loadCheckHistoryState() {
  const s = storage();
  if (!s) return { checkHistory: [], personCheckHistory: [], selectedCheckId: null, selectedPersonId: null };
  try {
    const raw = s.getItem(STORAGE_KEY);
    if (!raw) return { checkHistory: [], personCheckHistory: [], selectedCheckId: null, selectedPersonId: null };
    const data = JSON.parse(raw);
    return {
      checkHistory: Array.isArray(data.checkHistory) ? data.checkHistory.slice(0, MAX_CHECKS) : [],
      personCheckHistory: Array.isArray(data.personCheckHistory) ? data.personCheckHistory.slice(0, MAX_PERSON_CHECKS) : [],
      selectedCheckId: data.selectedCheckId || null,
      selectedPersonId: data.selectedPersonId || null,
    };
  } catch {
    return { checkHistory: [], personCheckHistory: [], selectedCheckId: null, selectedPersonId: null };
  }
}

export function saveCheckHistoryState({
  checkHistory = [],
  personCheckHistory = [],
  selectedCheckId = null,
  selectedPersonId = null,
} = {}) {
  const s = storage();
  if (!s) return false;
  const payload = {
    v: 1,
    savedAt: new Date().toISOString(),
    checkHistory: checkHistory.slice(0, MAX_CHECKS).map(trimRecord),
    personCheckHistory: personCheckHistory.slice(0, MAX_PERSON_CHECKS).map(trimRecord),
    selectedCheckId,
    selectedPersonId,
  };
  try {
    let text = JSON.stringify(payload);
    // Shrink oldest records if over quota.
    while (text.length > MAX_PAYLOAD_CHARS && payload.checkHistory.length > 1) {
      payload.checkHistory.pop();
      text = JSON.stringify(payload);
    }
    s.setItem(STORAGE_KEY, text);
    return true;
  } catch {
    try {
      // Last resort: keep only the selected record.
      const minimal = {
        v: 1,
        savedAt: new Date().toISOString(),
        checkHistory: payload.checkHistory.slice(0, 3).map(trimRecord),
        personCheckHistory: payload.personCheckHistory.slice(0, 3),
        selectedCheckId,
        selectedPersonId,
      };
      s.setItem(STORAGE_KEY, JSON.stringify(minimal));
      return true;
    } catch {
      return false;
    }
  }
}

export function persistFromAppState(state) {
  return saveCheckHistoryState({
    checkHistory: state.checkHistory || [],
    personCheckHistory: state.personCheckHistory || [],
    selectedCheckId: state.selectedCheckResult?.id || null,
    selectedPersonId: state.selectedPersonResult?.id || null,
  });
}

export function hydrateAppState(state) {
  const saved = loadCheckHistoryState();
  if (saved.checkHistory.length) {
    // Marks interrupted checks as failed so they are not stuck in «Проверяется».
    state.checkHistory = saved.checkHistory.map((r) => (
      r && r.status === 'Проверяется'
        ? { ...r, status: 'Ошибка проверки', findings: r.findings || 'Проверка прервана перезагрузкой страницы' }
        : r
    ));
  }
  if (saved.personCheckHistory.length) {
    state.personCheckHistory = saved.personCheckHistory.map((r) => (
      r && r.status === 'Проверяется'
        ? { ...r, status: 'Ошибка проверки', findings: r.findings || 'Проверка прервана перезагрузкой страницы' }
        : r
    ));
  }
  if (saved.selectedCheckId) {
    const rec = (state.checkHistory || []).find((r) => r.id === saved.selectedCheckId);
    if (rec) {
      state.selectedCheckResult = rec;
      // restore module panes from the record so the report is visible after F5
      state.companyFinances = rec.finances || null;
      state.companyFinancesError = rec.financesError || null;
      state.companyTimeline = rec.timeline || null;
      state.companyTimelineError = rec.timelineError || null;
    }
  }
  if (saved.selectedPersonId) {
    const rec = (state.personCheckHistory || []).find((r) => r.id === saved.selectedPersonId);
    if (rec) state.selectedPersonResult = rec;
  }
  return saved;
}
