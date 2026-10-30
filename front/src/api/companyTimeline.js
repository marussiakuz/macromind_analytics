/**
 * История событий и изменений (Checko timeline.md).
 * Контракт: data[] = [{ Дата, Событие }]
 */

export async function fetchCompanyTimeline(inn, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  timeoutMs = 35000,
} = {}) {
  if (!inn || !/^\d{10}$|^\d{12}$/.test(String(inn))) {
    return { status: 'error', message: 'Укажите ИНН организации или ИП.' };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(
      `${apiBase}/api/v1/companies/${encodeURIComponent(inn)}/timeline`,
      { signal: controller.signal },
    );
    let data;
    try {
      data = await response.json();
    } catch {
      return {
        status: 'error',
        message: 'Сервер вернул некорректный ответ по истории событий.',
      };
    }
    if (!response.ok) {
      return {
        status: 'error',
        message: typeof data.detail === 'string'
          ? data.detail
          : `Не удалось получить историю событий (${response.status})`,
      };
    }
    const timeline = data.timeline;
    if (!timeline || timeline.inn !== inn) {
      return {
        status: 'error',
        message: 'В ответе нет истории запрошенного контрагента.',
      };
    }
    const events = timeline.events || [];
    return {
      status: events.length ? 'ok' : 'empty',
      timeline,
      message: events.length ? null : 'События и изменения не найдены.',
    };
  } catch (error) {
    return {
      status: 'error',
      message: controller.signal.aborted
        ? 'Запрос истории событий не ответил вовремя.'
        : error instanceof TypeError
          ? 'Не удалось связаться с сервером для получения истории событий.'
          : error.message || 'Не удалось получить историю событий.',
    };
  } finally {
    clearTimeout(timer);
  }
}
