/**
 * Списочные реестры контрагента (legal-cases, enforcements, contracts,
 * fedresurs, bankruptcy-messages, inspections).
 */

export const REGISTRY_SECTIONS = [
  {
    method: 'legal-cases',
    key: 'legalCases',
    title: 'Арбитражные дела',
    subtitle: 'Иски, стороны и исходы из картотеки арбитражных дел',
  },
  {
    method: 'enforcements',
    key: 'enforcements',
    title: 'Исполнительные производства',
    subtitle: 'Сведения ФССП: предмет исполнения и задолженность',
  },
  {
    method: 'contracts',
    key: 'contracts',
    title: 'Госзакупки и контракты',
    subtitle: 'Контракты по 44-ФЗ и договоры по 223-ФЗ',
  },
  {
    method: 'fedresurs',
    key: 'fedresurs',
    title: 'Федресурс',
    subtitle: 'Сообщения о ликвидации, банкротстве и фактах деятельности',
  },
  {
    method: 'bankruptcy-messages',
    key: 'bankruptcy',
    title: 'Банкротства (ЕФРСБ)',
    subtitle: 'Публикации реестра банкротств',
  },
  {
    method: 'inspections',
    key: 'inspections',
    title: 'Проверки и КНМ',
    subtitle: 'Плановые и внеплановые проверки, нарушения и предписания',
  },
];

export async function fetchCompanyRegistry(method, inn, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  law = null,
  sort = '-date',
  limit = 100,
  timeoutMs = 35000,
} = {}) {
  if (!inn || !/^\d{10}$|^\d{12}$/.test(String(inn))) {
    return { status: 'error', message: 'Укажите ИНН организации или ИП.' };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const params = new URLSearchParams({ sort, limit: String(limit) });
    if (law) params.set('law', law);
    const response = await fetchImpl(
      `${apiBase}/api/v1/companies/${encodeURIComponent(inn)}/registry/${method}?${params.toString()}`,
      { signal: controller.signal },
    );
    let data;
    try {
      data = await response.json();
    } catch {
      return { status: 'error', message: 'Сервер вернул некорректный ответ реестра.' };
    }
    if (!response.ok) {
      return {
        status: 'error',
        message: typeof data.detail === 'string'
          ? data.detail
          : `Не удалось получить данные реестра (${response.status})`,
      };
    }
    const registry = data.registry;
    if (!registry || registry.inn !== inn) {
      return { status: 'error', message: 'В ответе нет данных запрошенного контрагента.' };
    }
    const items = registry.items || [];
    return {
      status: items.length ? 'ok' : 'empty',
      registry,
      message: items.length ? null : 'Записи не найдены.',
    };
  } catch (error) {
    return {
      status: 'error',
      message: controller.signal.aborted
        ? 'Запрос реестра не ответил вовремя.'
        : error instanceof TypeError
          ? 'Не удалось связаться с сервером для получения данных реестра.'
          : error.message || 'Не удалось получить данные реестра.',
    };
  } finally {
    clearTimeout(timer);
  }
}

/** Контракты: 44-ФЗ + 223-ФЗ, списки объединяются. */
export async function fetchContractsRegistry(inn, options = {}) {
  const [r44, r223] = await Promise.all([
    fetchCompanyRegistry('contracts', inn, { ...options, law: '44' }),
    fetchCompanyRegistry('contracts', inn, { ...options, law: '223' }),
  ]);
  const okParts = [r44, r223].filter(r => r.status === 'ok' || r.status === 'empty');
  if (!okParts.length) {
    return r44.status !== 'ok' ? r44 : r223;
  }
  const items = [...(r44.registry?.items || []), ...(r223.registry?.items || [])];
  return {
    status: items.length ? 'ok' : 'empty',
    registry: {
      ...(r44.registry || r223.registry || {}),
      inn,
      method: 'contracts',
      items,
      total: items.length,
    },
    message: items.length ? null : 'Записи не найдены.',
    partialError: (r44.status === 'error' || r223.status === 'error')
      ? (r44.message || r223.message)
      : null,
  };
}
