import {
  createStudy,
  getStudy,
  addEvidence,
  calculateTopDown,
  calculateBottomUp,
  triangulate,
  createBinding,
  listSummaries,
  addCompetitor,
  listCompetitors,
  calculateMDS,
  createExpertRound,
  addExpertResponse,
  closeExpertRound,
  buildMarketSummary,
  fetchAutoAnalysis,
  loadSavedAnalysis,
} from '../api/market.js';
import { marketState, resetMarketState } from './state.js';
import { hasEvidenceReport, hasFailedResearch } from './report-shape.js';
import { knowledgeSearch } from '../api/knowledge.js';

const API_BASE = 'http://localhost:8000';
/** F26–F27: поздний ответ старого запроса не заменяет новый результат. */
let autoAnalysisToken = 0;
let lastAutoInput = null;

/**
 * Обработчики блока «Анализ рынка и конкурентов».
 * Не тянет внешний поиск — только сохранённые расчёты и ручные данные.
 */
export function setupMarketListeners(renderApp, { getInn, getCompanyName } = {}) {
  document.getElementById('market-refresh-analysis')?.addEventListener('click', async () => {
    if (!lastAutoInput) return;
    const task = runAutoMarketAnalysis({ ...lastAutoInput, force: true, requestId: undefined });
    renderApp();
    await task;
    renderApp();
  });
  document.querySelectorAll('#market-open-detail').forEach((btn) => {
    btn.addEventListener('click', () => {
      marketState.detailOpen = true;
      marketState.error = null;
      renderApp();
      document.getElementById('market-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.getElementById('market-download-report')?.addEventListener('click', async () => {
    if (marketState.summary?.report_html) {
      const blob = new Blob([marketState.summary.report_html], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `market-${marketState.summary.legal_entity_inn || 'report'}.html`;
      document.body.appendChild(a);
      a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
      return;
    }
    const studyId = marketState.studyId;
    if (!studyId) {
      marketState.error = 'Сначала создайте исследование — затем можно скачать отчет.';
      renderApp();
      return;
    }
    try {
      marketState.loading = true;
      renderApp();
      const filename = await downloadMarketReport(studyId);
      marketState.error = null;
      marketState.loading = false;
      renderApp();
      // success is shown after file is created (plan §4.3)
      import('../notifications.js').then(({ showNotification }) => {
        showNotification(`Отчет сохранен: ${filename}`, 'success');
      });
    } catch (e) {
      marketState.loading = false;
      marketState.error = e.message || 'Не удалось выгрузить отчет.';
      renderApp();
    }
  });

  document.getElementById('market-close-detail')?.addEventListener('click', () => {
    marketState.detailOpen = false;
    renderApp();
    document.getElementById('market-area')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  document.getElementById('market-knowledge-search-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = (document.getElementById('market-knowledge-query')?.value || '').trim();
    if (question.length < 3) {
      marketState.knowledgeError = 'Введите запрос не короче трёх символов.';
      marketState.knowledgeResult = null;
      renderApp();
      return;
    }
    marketState.knowledgeQuery = question;
    marketState.knowledgeError = null;
    marketState.knowledgeLoading = true;
    marketState.knowledgeResult = null;
    renderApp();
    try {
      const result = await knowledgeSearch({ question, mode: 'hybrid' });
      marketState.knowledgeResult = result;
      marketState.knowledgeError = null;
    } catch (err) {
      marketState.knowledgeResult = null;
      marketState.knowledgeError = err?.message || 'Поиск недоступен.';
    } finally {
      marketState.knowledgeLoading = false;
      renderApp();
    }
  });

  document.getElementById('market-link-deal')?.addEventListener('click', async () => {
    const inn = getInn?.();
    if (!marketState.studyId) {
      marketState.error = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    try {
      marketState.loading = true;
      renderApp();
      await createBinding(marketState.studyId, {
        legal_entity_inn: inn || null,
        product_scope_id: marketState.study?.market_scope?.product || null,
      }, { apiBase: API_BASE });
      const sums = await listSummaries({ legal_entity_inn: inn || undefined }, { apiBase: API_BASE });
      marketState.summary = buildMarketSummary({
        study: marketState.study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: sums.items || [],
      });
      marketState.error = null;
    } catch (e) {
      marketState.error = e.message || 'Не удалось связать исследование.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-create-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const product = form.product.value.trim();
    if (!product) {
      marketState.error = 'Укажите продукт и границы рынка.';
      renderApp();
      return;
    }
    const payload = {
      title: product,
      scope: {
        product,
        buyer: form.buyer.value.trim() || null,
        countries: form.countries.value.split(',').map((s) => s.trim()).filter(Boolean),
        reference_period: form.reference_period.value.trim() || null,
        measure_type: 'revenue',
      },
    };
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      let study;
      if (marketState.studyId) {
        study = await getStudy(marketState.studyId, { apiBase: API_BASE });
      } else {
        study = await createStudy(payload, { apiBase: API_BASE });
      }
      marketState.study = study;
      marketState.studyId = study.id;
      // сводка сразу после паспорта
      marketState.summary = buildMarketSummary({
        study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: marketState.bindings,
      });
    } catch (err) {
      marketState.error = err.message || 'Не удалось сохранить паспорт.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-evidence-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.error = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      await addEvidence(marketState.studyId, {
        metric: form.metric.value.trim(),
        value: form.value.value.trim() || null,
        unit: form.unit.value.trim() || 'unit',
        source_id: form.source_id.value.trim() || 'manual',
        source_locator: form.source_locator.value.trim() || null,
        status: 'unreviewed',
      }, { apiBase: API_BASE });
      form.reset();
    } catch (err) {
      marketState.error = err.message || 'Не удалось добавить наблюдение.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-topdown-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.error = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    const shares = form.shares.value.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      marketState.topDown = await calculateTopDown(marketState.studyId, {
        base: form.base.value.trim(),
        shares,
      }, { apiBase: API_BASE });
      marketState.summary = buildMarketSummary({
        study: marketState.study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: marketState.bindings,
      });
    } catch (err) {
      marketState.error = err.message || 'Ошибка расчёта сверху вниз.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-bottomup-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.error = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    const n = Number(form.n.value);
    const acv = form.acv.value.trim();
    const p = form.p.value.trim();
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      const segment = {
        name: 'segment-1',
        n_eligible: n,
        acv_potential: acv,
        p_buy: p || null,
        acv_buyers: p ? acv : null,
      };
      marketState.bottomUp = await calculateBottomUp(marketState.studyId, {
        segments: [segment],
      }, { apiBase: API_BASE });
      marketState.summary = buildMarketSummary({
        study: marketState.study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: marketState.bindings,
      });
    } catch (err) {
      marketState.error = err.message || 'Ошибка расчёта снизу вверх.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-triangulate')?.addEventListener('click', async () => {
    if (!marketState.studyId || !marketState.topDown || !marketState.bottomUp) return;
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      marketState.triangulation = await triangulate(marketState.studyId, {
        a_value: marketState.topDown.value,
        b_value: marketState.bottomUp.potential?.value,
        a_kind: 'potential',
        b_kind: 'potential',
      }, { apiBase: API_BASE });
      marketState.summary = buildMarketSummary({
        study: marketState.study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: marketState.bindings,
      });
    } catch (err) {
      marketState.error = err.message || 'Ошибка сопоставления.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-competitor-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.error = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    try {
      marketState.loading = true;
      marketState.error = null;
      renderApp();
      await addCompetitor(marketState.studyId, {
        company_name: form.company_name.value.trim(),
        product_name: form.product_name.value.trim(),
        kind: 'direct',
      }, { apiBase: API_BASE });
      const listed = await listCompetitors(marketState.studyId, { apiBase: API_BASE });
      marketState.competitors = listed.included || [];
      marketState.summary = buildMarketSummary({
        study: marketState.study,
        topDown: marketState.topDown,
        bottomUp: marketState.bottomUp,
        triangulation: marketState.triangulation,
        bindings: marketState.bindings,
        competitor_findings: (listed.included || []).map(c => `${c.company_name} / ${c.product_name}`),
        limitations: listed.incompleteness_note ? [listed.incompleteness_note] : [],
      });
      form.reset();
    } catch (err) {
      marketState.error = err.message || 'Не удалось добавить конкурента.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-mds-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.mdsError = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    const f1 = form.f1.value.trim() || 'f1';
    const f2 = form.f2.value.trim() || 'f2';
    const scales = form.scales.value.split(',').map(x => Number(x.trim())).filter(x => Number.isFinite(x) && x > 0);
    const scale1 = scales[0] ?? 1;
    const scale2 = scales[1] ?? 1;
    const objects = [];
    try {
      form.rows.value.split('\n').forEach((line) => {
        const t = line.trim();
        if (!t) return;
        const parts = t.split(',').map(x => x.trim());
        if (parts.length < 3) throw new Error(`Строка «${t}»: нужно id, признак1, признак2`);
        const v1 = parts[1] === '' || parts[1] === '-' ? null : Number(parts[1]);
        const v2 = parts[2] === '' || parts[2] === '-' ? null : Number(parts[2]);
        if (v1 != null && !Number.isFinite(v1)) throw new Error(`Строка «${t}»: признак1 не число`);
        if (v2 != null && !Number.isFinite(v2)) throw new Error(`Строка «${t}»: признак2 не число`);
        objects.push({ id: parts[0], values: { [f1]: v1, [f2]: v2 } });
      });
    } catch (parseErr) {
      marketState.mdsError = parseErr.message;
      renderApp();
      return;
    }
    try {
      marketState.loading = true;
      marketState.mdsError = null;
      renderApp();
      marketState.mds = await calculateMDS(marketState.studyId, {
        objects,
        features: [
          { name: f1, scale: scale1, weight: 0.5 },
          { name: f2, scale: scale2, weight: 0.5 },
        ],
      }, { apiBase: API_BASE });
    } catch (err) {
      marketState.mds = null;
      marketState.mdsError = err.message || 'Ошибка построения карты.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-delphi-round-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId) {
      marketState.delphiError = 'Сначала создайте исследование.';
      renderApp();
      return;
    }
    const form = e.target;
    try {
      marketState.loading = true;
      marketState.delphiError = null;
      renderApp();
      const round = await createExpertRound(marketState.studyId, {
        question: form.question.value.trim(),
        unit: form.unit.value.trim() || 'RUB',
      }, { apiBase: API_BASE });
      marketState.delphiRoundId = round.id;
      marketState.delphiSummary = null;
      form.reset();
    } catch (err) {
      marketState.delphiError = err.message || 'Не удалось создать раунд.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-delphi-response-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!marketState.studyId || !marketState.delphiRoundId) return;
    const form = e.target;
    try {
      marketState.loading = true;
      marketState.delphiError = null;
      renderApp();
      await addExpertResponse(marketState.studyId, marketState.delphiRoundId, {
        participant: form.participant.value.trim(),
        value: form.value.value.trim() || null,
        explanation: form.explanation.value.trim() || null,
      }, { apiBase: API_BASE });
      form.reset();
    } catch (err) {
      marketState.delphiError = err.message || 'Не удалось добавить ответ.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });

  document.getElementById('market-delphi-close')?.addEventListener('click', async () => {
    if (!marketState.studyId || !marketState.delphiRoundId) return;
    try {
      marketState.loading = true;
      marketState.delphiError = null;
      renderApp();
      marketState.delphiSummary = await closeExpertRound(
        marketState.studyId,
        marketState.delphiRoundId,
        { apiBase: API_BASE },
      );
    } catch (err) {
      marketState.delphiError = err.message || 'Не удалось закрыть раунд.';
    } finally {
      marketState.loading = false;
      renderApp();
    }
  });
}

/** Collect Checko company fields into site_text / urls for product extraction. */
function companySourceContext(company) {
  if (!company) return { siteText: null, urls: [] };
  const contacts = company.contacts || {};
  const website = contacts['ВебСайт'] || contacts.ВебСайт || contacts.website || contacts.Сайт || '';
  const parts = [];
  if (company.full_name || company.name) parts.push(`${company.full_name || company.name}`);
  if (company.okved_description) parts.push(`ОКВЭД: ${company.okved_description}`);
  if (company.okved_main) parts.push(`код ${company.okved_main}`);
  if (website) parts.push(`Официальный сайт: ${website}`);
  if (company.director) parts.push(`Руководитель: ${company.director}`);
  const urls = [website, ...(company.urls || [])].filter(Boolean);
  return {
    siteText: parts.length ? parts.join('. ') : null,
    urls,
    website,
  };
}

/** Автоанализ рынка после загрузки реестров — без ручных кнопок расчёта. */
export async function runAutoMarketAnalysis({ company, finances, registries, requestId, force = false, siteText = null }) {
  lastAutoInput = { company, finances, registries, siteText };
  const token = requestId ?? ++autoAnalysisToken;
  autoAnalysisToken = token;
  const inn = company?.inn;
  const ctx = companySourceContext(company);
  const requestKey = `auto-${inn || 'anon'}-${globalThis.crypto.randomUUID()}`;
  let progressTimer = null;
  let polling = false;
  const phaseLabels = {
    model_readiness: 'Проверяем доступность модели…',
    company_sources: 'Ищем и читаем источники о компании…',
    company_profile: 'Проверяем сайт и определяем направления бизнеса…',
    market_sources: 'Собираем материалы о рынке и технологиях…',
    competitor_research: 'Ищем и проверяем кандидатов в конкуренты…',
    report_and_audit: 'Готовим отчёт и проверяем выводы по источникам…',
    saving: 'Сохраняем отчёт…',
  };
  try {
    marketState.loading = true;
    marketState.error = null;
    // F25: saved version — but NOT if it was saved without external sources
    // (stale "not_configured" cache must not freeze a dead report).
    if (inn && !force) {
      try {
        const saved = await loadSavedAnalysis({ legal_entity_inn: inn }, { apiBase: API_BASE });
        const states = saved?.external_source_states || [];
        const staleSources = states.length > 0 && states.every(
          s => s.status === 'not_configured' || s.status === 'error',
        );
        if (hasEvidenceReport(saved) && !staleSources
            && !hasFailedResearch(saved)
            && autoAnalysisToken === token) {
          marketState.summary = saved;
          marketState.studyId = saved.study_id || marketState.studyId;
          marketState.topDown = saved.estimates_rf || null;
          return saved;
        }
      } catch {
        /* нет сохранённой версии */
      }
    }
    marketState.progress = 'Проверяем доступность модели…';
    progressTimer = setInterval(async () => {
      if (polling || autoAnalysisToken !== token) return;
      polling = true;
      try {
        const response = await fetch(`${API_BASE}/api/v1/market/auto-analysis/progress?request_key=${encodeURIComponent(requestKey)}`, { signal: AbortSignal.timeout(4000) });
        if (!response.ok) return;
        const progress = await response.json();
        if (autoAnalysisToken !== token) return;
        marketState.progress = phaseLabels[progress.step] || 'Выполняем исследование…';
        const node = document.getElementById('market-progress');
        if (node) node.textContent = marketState.progress;
      } catch { /* A failed progress request must not cancel research. */ }
      finally { polling = false; }
    }, 2000);
    const summary = await fetchAutoAnalysis({
      company: {
        ...(company || {}),
        // Checko website → product discovery input
        site: ctx.website || company?.site || null,
        website: ctx.website || company?.website || null,
      },
      finances: finances || null,
      registries: registries || {},
      site_text: siteText || ctx.siteText || company?.site_text || company?.description || null,
      extra_sources: ctx.urls.length ? ctx.urls : null,
      request_key: requestKey,
      use_external_evidence: true,
      use_discovery: true,
      use_llm: true,
    }, { apiBase: API_BASE });
    if (autoAnalysisToken !== token) return null; // F26
    marketState.summary = summary;
    marketState.studyId = summary.study_id || marketState.studyId;
    marketState.topDown = summary.estimates_rf || null;
    return summary;
  } catch (e) {
    if (autoAnalysisToken !== token) return null; // F27
    marketState.error = e.message || 'Не удалось построить анализ рынка.';
    return null;
  } finally {
    if (progressTimer !== null) clearInterval(progressTimer);
    if (autoAnalysisToken === token) {
      marketState.loading = false;
      marketState.progress = null;
    }
  }
}

/** F28: загрузка анализа, привязанного к сделке (ИНН проекта / project_id). */
export async function loadDealMarketSummary({ inn, projectId } = {}) {
  marketState.dealLoading = true;
  marketState.dealError = null;
  try {
    const saved = await loadSavedAnalysis(
      { legal_entity_inn: inn || undefined, study_id: undefined },
      { apiBase: API_BASE },
    );
    if (saved) {
      marketState.dealSummary = saved;
      marketState.dealError = null;
    } else {
      marketState.dealSummary = null;
      marketState.dealError = 'Для этой заявки исследование рынка не найдено.';
    }
  } catch {
    marketState.dealSummary = null;
    marketState.dealError = 'Для этой заявки исследование рынка не найдено.';
  } finally {
    marketState.dealLoading = false;
    return marketState.dealSummary;
  }
}

/** Загрузка сводок по ИНН при открытии проверки компании (без нового поиска). */
export async function loadMarketSummaryForInn(inn, companyContext = null) {
  if (!inn) return null;
  try {
    const sums = await listSummaries({ legal_entity_inn: inn }, { apiBase: API_BASE });
    const first = (sums.items || [])[0];
    if (!first) {
      marketState.bindings = [];
      // черновик из данных компании, чтобы блок не был «пустым» без пояснения
      marketState.summary = buildMarketSummary({
        study: {
          id: null,
          version: null,
          as_of: null,
          market_scope: {
            product: companyContext?.okved_description || companyContext?.name || '',
            buyer: null,
            countries: ['RU'],
            reference_period: null,
            measure_type: 'revenue',
          },
        },
        topDown: null,
        bottomUp: null,
        triangulation: null,
        bindings: [],
      });
      marketState.summary.review_status = 'not_started';
      marketState.summary.limitations = [
        'Исследование еще не создано. Нажмите «Открыть исследование» и заполните паспорт рынка.',
      ];
      return marketState.summary;
    }
    marketState.bindings = sums.items || [];
    marketState.studyId = first.study_id;
    marketState.summary = {
      study_id: first.study_id,
      report_version: first.report_version,
      binding_revision: first.binding_revision,
      legal_entity_inn: first.legal_entity_inn,
      product_scope_id: first.product_scope_id,
      market_scope: first.market_scope,
      reference_period: first.market_scope?.reference_period || null,
      as_of: null,
      estimates_rf: marketState.topDown,
      estimates_world: null,
      triangulation_status: marketState.triangulation?.status || 'insufficient_data',
      competitor_findings: [],
      technology_findings: [],
      limitations: [],
      data_completeness: {
        has_top_down: !!marketState.topDown?.value,
        has_bottom_up: !!marketState.bottomUp?.potential?.value,
        has_triangulation: !!marketState.triangulation?.status,
      },
      review_status: first.review_status || 'draft',
      freshness: null,
      evidence_refs: [],
    };
    return marketState.summary;
  } catch {
    marketState.summary = null;
    return null;
  }
}

/** Скачать HTML-отчет с рыночным разделом (plan §4.3). */
export async function downloadMarketReport(studyId) {
  if (!studyId) throw new Error('Нет активного исследования');
  const res = await fetch(`${API_BASE}/api/v1/market/studies/${encodeURIComponent(studyId)}/report`);
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error('Сервер вернул некорректный отчет');
  }
  if (!res.ok) throw new Error(data?.detail || 'Не удалось получить отчет');
  const blob = new Blob([data.html], { type: data.content_type || 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = data.filename || 'market-report.html';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return data.filename;
}

export { resetMarketState };
