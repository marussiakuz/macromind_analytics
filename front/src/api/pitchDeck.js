/**
 * Pitch deck analysis API (/api/v1/pitchdeck).
 * Decks are processed by a local model only; see backend pitchdeck package.
 */

const DEFAULT_API = 'http://localhost:8000';

async function readJson(res) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    const error = new Error(message || `Ошибка сервиса: HTTP ${res.status}`);
    error.status = res.status;
    error.code = detail?.code;
    throw error;
  }
  return body;
}

export async function fetchModelStatus({ apiBase = DEFAULT_API, fetchImpl = globalThis.fetch } = {}) {
  return readJson(await fetchImpl(`${apiBase}/api/v1/pitchdeck/status`));
}

export async function uploadDeck(file, { apiBase = DEFAULT_API, fetchImpl = globalThis.fetch } = {}) {
  const form = new FormData();
  form.append('file', file);
  return readJson(await fetchImpl(`${apiBase}/api/v1/pitchdeck/analyses`, { method: 'POST', body: form }));
}

export async function listAnalyses({ apiBase = DEFAULT_API, fetchImpl = globalThis.fetch } = {}) {
  return readJson(await fetchImpl(`${apiBase}/api/v1/pitchdeck/analyses`));
}

export async function getAnalysis(id, { apiBase = DEFAULT_API, fetchImpl = globalThis.fetch } = {}) {
  return readJson(await fetchImpl(`${apiBase}/api/v1/pitchdeck/analyses/${encodeURIComponent(id)}`));
}

export async function deleteAnalysis(id, { apiBase = DEFAULT_API, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${apiBase}/api/v1/pitchdeck/analyses/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) await readJson(res);
}

export function slideImageUrl(id, number, apiBase = DEFAULT_API) {
  return `${apiBase}/api/v1/pitchdeck/analyses/${encodeURIComponent(id)}/slides/${number}/image`;
}
