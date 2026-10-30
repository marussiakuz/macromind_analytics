/**
 * Market research API (/api/v1/market).
 * Summary format per plan §4.4 MarketSummary.
 */

export async function createStudy(payload, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson(res);
}

export async function getStudy(studyId, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}`);
  return readJson(res);
}

export async function listStudies(params = {}, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const q = new URLSearchParams();
  if (params.owner) q.set('owner', params.owner);
  if (params.limit) q.set('limit', String(params.limit));
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies${q.toString() ? `?${q}` : ''}`);
  return readJson(res);
}

export async function addEvidence(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/evidence`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function calculateTopDown(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/calculate/top-down`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function calculateBottomUp(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/calculate/bottom-up`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function triangulate(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/triangulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function createBinding(studyId, extra = {}, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const q = new URLSearchParams({ study_id: studyId });
  Object.entries(extra).forEach(([k, v]) => {
    if (v != null && v !== '') q.set(k, String(v));
  });
  const res = await fetchImpl(`${apiBase}/api/v1/market/bindings?${q.toString()}`, { method: 'POST' });
  return readJson(res);
}

export async function listSummaries(params = {}, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const q = new URLSearchParams();
  if (params.legal_entity_inn) q.set('legal_entity_inn', params.legal_entity_inn);
  if (params.project_id) q.set('project_id', params.project_id);
  const res = await fetchImpl(`${apiBase}/api/v1/market/summaries${q.toString() ? `?${q}` : ''}`);
  return readJson(res);
}

export async function addCompetitor(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/competitors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function listCompetitors(studyId, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/competitors`);
  return readJson(res);
}

export async function calculateMDS(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/mds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function createExpertRound(studyId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/expert-rounds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function addExpertResponse(studyId, roundId, body, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(
    `${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/expert-rounds/${encodeURIComponent(roundId)}/responses`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return readJson(res);
}

export async function closeExpertRound(studyId, roundId, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(
    `${apiBase}/api/v1/market/studies/${encodeURIComponent(studyId)}/expert-rounds/${encodeURIComponent(roundId)}/close`,
    { method: 'POST' },
  );
  return readJson(res);
}

/** Автоматический анализ из данных реестров (без ручных расчётов). */
export async function fetchAutoAnalysis(payload, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/market/auto-analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson(res);
}

/** Восстановление сохранённой версии без повторного вызова модели (F25). */
export async function loadSavedAnalysis(params = {}, { apiBase = 'http://localhost:8000', fetchImpl = globalThis.fetch } = {}) {
  const q = new URLSearchParams();
  if (params.legal_entity_inn) q.set('legal_entity_inn', params.legal_entity_inn);
  if (params.study_id) q.set('study_id', params.study_id);
  if (params.version_id) q.set('version_id', params.version_id);
  const res = await fetchImpl(`${apiBase}/api/v1/market/auto-analysis?${q.toString()}`);
  return readJson(res);
}

async function readJson(res) {
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error('Сервер вернул некорректный ответ рынка.');
  }
  if (!res.ok) {
    const detail = data?.detail;
    const err = detail?.error;
    if (err?.message) {
      const e = new Error(err.message);
      e.code = err.code;
      e.fields = err.fields;
      throw e;
    }
    throw new Error(typeof detail === 'string' ? detail : `Ошибка API рынка (${res.status})`);
  }
  return data;
}

/** Сводка MarketSummary для карточки (plan §4.1). */
export function buildMarketSummary({
  study,
  topDown,
  bottomUp,
  triangulation,
  bindings,
  competitor_findings = [],
  limitations = [],
}) {
  return {
    study_id: study?.id || null,
    report_version: study?.version ?? null,
    binding_revision: bindings?.[0]?.binding_revision ?? null,
    legal_entity_inn: bindings?.[0]?.legal_entity_inn ?? null,
    product_scope_id: bindings?.[0]?.product_scope_id ?? null,
    market_scope: study?.market_scope || null,
    reference_period: study?.market_scope?.reference_period || null,
    as_of: study?.as_of || null,
    estimates_rf: topDown || null,
    estimates_world: null,
    triangulation_status: triangulation?.status || 'insufficient_data',
    competitor_findings,
    technology_findings: [],
    limitations,
    data_completeness: {
      has_top_down: !!topDown?.value,
      has_bottom_up: !!bottomUp?.potential?.value,
      has_triangulation: !!triangulation?.status,
    },
    review_status: 'draft',
    freshness: study?.as_of || null,
    evidence_refs: [],
  };
}
