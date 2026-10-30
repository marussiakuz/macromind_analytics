/**
 * Поиск организаций/ИП по search.md (Checko).
 * Тип поиска определяется автоматически по содержимому строки
 * либо задаётся явно пользователем (searchTypeOverride).
 */

// ОКВЭД-2: класс (62), подкласс (62.0), группа (62.01), подгруппа (62.01.1), вид (62.01.11)
const OKVED_RE = /^\d{2}(\.\d{1,3}){0,3}$/;

export function detectSearchType(raw) {
  const value = String(raw || '').trim();
  if (!value) return null;
  if (value.includes('@') || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'email';
  // dates before phones: 2020-12-31 must not look like a phone
  if (/^\d{4}-\d{2}-\d{2}$/.test(value) || /^\d{2}\.\d{2}\.\d{4}$/.test(value)) {
    return 'reg-date';
  }
  if (/^(reg|upd)[\s:-]/i.test(value) && /\d/.test(value)) {
    return /^upd/i.test(value) ? 'upd-date' : 'reg-date';
  }
  if (/^founder[:\s-]/i.test(value)) return 'founder-name';
  if (/^leader[:\s-]/i.test(value)) return 'leader-name';
  if (OKVED_RE.test(value)) return 'okved';
  if (/^[\d\s\-()+]+$/.test(value)) {
    const digits = value.replace(/\D/g, '');
    if (digits.length >= 7) return 'phone';
  }
  return 'name';
}

export function normalizeSearchQuery(raw, by) {
  let value = String(raw || '').trim();
  if (by === 'founder-name' || by === 'leader-name') {
    value = value.replace(/^(founder|leader)[:\s-]+/i, '');
  }
  if (by === 'reg-date' || by === 'upd-date') {
    value = value.replace(/^(reg|upd)[:\s-]+/i, '');
    // normalize 31.12.2020 -> 2020-12-31
    const ru = value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
    if (ru) value = `${ru[3]}-${ru[2]}-${ru[1]}`;
  }
  return value.trim();
}

/** Min length depends on search type (search.md). */
export function validateSearchQuery(query, by) {
  if (!query) return 'Введите поисковый запрос.';
  if (by === 'name' || by === 'founder-name' || by === 'leader-name') {
    if (query.length < 4) return 'Для поиска по наименованию/ФИО нужно минимум 4 символа.';
    return null;
  }
  if (by === 'okved') {
    if (!OKVED_RE.test(query)) return 'Некорректный код ОКВЭД. Примеры: 62, 62.01, 62.01.1, 62.01.11.';
    return null;
  }
  if (by === 'phone') {
    if (query.replace(/\D/g, '').length < 7) return 'Слишком короткий номер телефона.';
    return null;
  }
  if (by === 'email') {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(query)) return 'Некорректный email.';
    return null;
  }
  if (by === 'reg-date' || by === 'upd-date') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(query)) return 'Укажите дату в формате ГГГГ-ММ-ДД.';
    return null;
  }
  return null;
}

export async function searchCompanies(rawQuery, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  obj = 'org',
  limit = 20,
  page = 1,
  region = null,
  okved = null,
  opf = null,
  active = null,
  codes = null,
  searchTypeOverride = null,
  timeoutMs = 35000,
} = {}) {
  const by = searchTypeOverride || detectSearchType(rawQuery);
  const query = normalizeSearchQuery(rawQuery, by);
  const invalid = validateSearchQuery(query, by);
  if (!by || invalid) {
    throw new Error(invalid || 'Введите поисковый запрос.');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const params = new URLSearchParams({
      q: query,
      by,
      obj,
      limit: String(limit),
      page: String(page),
    });
    if (region) params.set('region', region);
    if (okved) params.set('okved', okved);
    if (opf) params.set('opf', opf);
    if (codes) params.set('codes', codes);
    if (active === true) params.set('active', 'true');
    if (active === false) params.set('active', 'false');

    const response = await fetchImpl(
      `${apiBase}/api/v1/companies/search?${params.toString()}`,
      { signal: controller.signal },
    );
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error('Сервер вернул некорректный ответ поиска.');
    }
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка поиска (${response.status})`);
    }
    return {
      by,
      obj,
      query,
      page: data.page ?? page,
      totalPages: data.total_pages ?? null,
      results: data.results || [],
      source: data.source || 'checko',
      balance: data.balance ?? null,
      todayRequestCount: data.today_request_count ?? null,
    };
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error('Поиск не ответил вовремя. Повторите попытку.');
    }
    if (error instanceof TypeError) {
      throw new Error(
        'Не удалось связаться с сервером поиска. Проверьте, что API запущен на localhost:8000, и повторите попытку.',
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
