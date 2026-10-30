/**
 * Knowledge base API (/api/v1/knowledge) — Task2 Stage E/D.
 * Empty search result is normal, not an error (§12).
 * Auth: X-Api-Key / Bearer KNOWLEDGE_INTERNAL_TOKEN (access.py).
 */

const DEFAULT_BASE = 'http://localhost:8000';

function knowledgeToken() {
  try {
    return (
      (typeof import.meta !== 'undefined' && import.meta.env?.VITE_KNOWLEDGE_API_KEY) ||
      (typeof localStorage !== 'undefined' && localStorage.getItem('mma_knowledge_token')) ||
      ''
    );
  } catch {
    return '';
  }
}

function authHeaders(extra = {}) {
  const token = knowledgeToken();
  const headers = { 'Content-Type': 'application/json', ...extra };
  if (token) {
    headers['X-Api-Key'] = token;
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function readJson(res) {
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text.slice(0, 200) };
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === 'string' ? detail : (detail?.message || `HTTP ${res.status}`);
    const err = new Error(msg);
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data;
}

export async function knowledgeSearch(payload, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/search`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return readJson(res);
}

export async function knowledgeIngest(payload, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/ingestions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return readJson(res);
}

export async function knowledgeBridgeMarket(summary, opts = {}, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/bridge/market`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ summary, ...opts }),
  });
  return readJson(res);
}

export async function listKnowledgeSignals(params = {}, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const q = new URLSearchParams();
  if (params.workspace_id) q.set('workspace_id', String(params.workspace_id));
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/signals${q.toString() ? `?${q}` : ''}`, {
    headers: authHeaders(),
  });
  return readJson(res);
}

export async function recordKnowledgeEvent(body, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/signals/events`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function createKnowledgeHypothesis(body, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/signals/hypotheses`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function getEvidence(evidenceId, { apiBase = DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/knowledge/evidence/${encodeURIComponent(evidenceId)}`, {
    headers: authHeaders(),
  });
  return readJson(res);
}
