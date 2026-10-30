/**
 * Финансовая отчетность организации (Checko finances.md).
 * Контракт: data[год][2110] — выручка, data[год][2400] — чистая прибыль.
 */

export async function fetchCompanyFinances(inn, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  timeoutMs = 60000,
} = {}) {
  if (!inn || !/^\d{10}$/.test(String(inn))) {
    return { status: 'skipped', reason: 'Для организаций с ИНН 10 цифр' };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(
      `${apiBase}/api/v1/companies/${encodeURIComponent(inn)}/finances`,
      { signal: controller.signal },
    );
    let data;
    try {
      data = await response.json();
    } catch {
      return {
        status: 'error',
        message: 'Сервер вернул некорректный ответ по финансовой отчетности.',
      };
    }
    if (!response.ok) {
      return {
        status: 'error',
        message: typeof data.detail === 'string'
          ? data.detail
          : `Не удалось получить финансовую отчетность (${response.status})`,
      };
    }
    const finances = data.finances;
    if (!finances || finances.inn !== inn) {
      return {
        status: 'error',
        message: 'В ответе нет финансовых данных запрошенной компании.',
      };
    }
    const years = finances.years || [];
    const hasFigures = years.some(y => y.revenue != null || y.net_profit != null);
    return {
      status: hasFigures ? 'ok' : 'empty',
      finances,
      message: hasFigures ? null : 'Финансовая отчетность за доступные годы не найдена.',
    };
  } catch (error) {
    return {
      status: 'error',
      message: controller.signal.aborted
        ? 'Запрос финансовой отчетности не ответил вовремя.'
        : error instanceof TypeError
          ? 'Не удалось связаться с сервером для получения финансовой отчетности.'
          : error.message || 'Не удалось получить финансовую отчетность.',
    };
  } finally {
    clearTimeout(timer);
  }
}
