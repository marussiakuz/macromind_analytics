const personRiskLabels = {
  unfair_supplier: 'Реестр недобросовестных поставщиков',
  mass_director: 'Массовый руководитель',
  mass_founder: 'Массовый учредитель',
  sanctioned: 'Санкции в отношении физлица',
};

/** Max concurrent auto-checks after a company lookup (API quota). */
export const MAX_AUTO_PERSON_CHECKS = 5;

/**
 * Collect unique people from directors and founders of a company.
 * One person may have several roles; INN is the stable id.
 * @param {object} company — normalized company payload
 * @returns {{inn: string|null, name: string, roles: string[], checkStatus: string, person?: object, findings?: string}[]}
 */
export function extractPersonInns(company) {
  if (!company) return [];
  const found = new Map();

  function upsert(name, inn, role) {
    const key = inn || `name:${name}`;
    const existing = found.get(key);
    if (existing) {
      if (!existing.roles.includes(role)) existing.roles.push(role);
      return;
    }
    found.set(key, {
      inn: inn || null,
      name: name || inn || 'Без имени',
      roles: [role],
      checkStatus: inn ? 'not_checked' : 'no_inn',
      person: null,
      findings: inn ? null : 'Автоматическая проверка недоступна: нет ИНН',
    });
  }

  for (const d of company.directors || []) {
    const inn = String(d['ИНН'] || d.ИНН || '').trim();
    const name = String(d['ФИО'] || d.ФИО || '').trim();
    upsert(name, /^\d{12}$/.test(inn) ? inn : null, 'Руководитель');
  }
  for (const s of company.shareholders || []) {
    const inn = String(s.inn || '').trim();
    const name = String(s.name || '').trim();
    upsert(name, s.type === 'person' && /^\d{12}$/.test(inn) ? inn : null, 'Учредитель');
  }
  return [...found.values()];
}

/**
 * First batch of people that can be auto-checked (has INN, not yet checked).
 * @param {object[]} people
 * @param {number} limit
 */
export function selectAutoBatch(people, limit = MAX_AUTO_PERSON_CHECKS) {
  return (people || [])
    .filter(p => p.inn && (p.checkStatus === 'not_checked' || p.checkStatus === 'error'))
    .slice(0, limit);
}

export async function completePersonCheck(record, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  timeoutMs = 35000,
} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(
      `${apiBase}/api/v1/persons/${encodeURIComponent(record.inn)}`,
      { signal: controller.signal },
    );
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error('Сервер вернул некорректный ответ. Повторите проверку.');
    }
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка сервера (${response.status})`);
    }
    const person = data.person;
    if (!person || person.inn !== record.inn || !person.full_name) {
      throw new Error('В ответе нет данных запрошенного физлица. Повторите проверку.');
    }
    const risks = Object.entries(person.risk_factors || {})
      .filter(([key, value]) => value === true && key !== 'sanctioned_countries')
      .map(([key]) => personRiskLabels[key] || key);
    const countries = person.risk_factors?.sanctioned_countries || [];
    if (countries.length) {
      risks.push(`Санкции стран: ${countries.join(', ')}`);
    }
    const summary = [];
    summary.push(`ФИО: ${person.full_name}`);
    if (person.managed_companies?.length) {
      summary.push(`Руководитель в организациях: ${person.managed_companies.length}`);
    }
    if (person.founded_companies?.length) {
      summary.push(`Учредитель в организациях: ${person.founded_companies.length}`);
    }
    if (person.entrepreneurships?.length) {
      summary.push(`ИП: ${person.entrepreneurships.length}`);
    }
    if (risks.length) summary.push(`Факторы риска: ${risks.join('; ')}`);
    else summary.push('В полученных сведениях нет отмеченных факторов риска.');
    Object.assign(record, {
      name: person.full_name,
      status: 'Анализ завершен',
      person,
      source: data.source || 'checko',
      findings: summary.join('\n'),
      riskLevel: risks.length ? 'Требует внимания' : null,
    });
  } catch (error) {
    Object.assign(record, {
      status: 'Ошибка проверки',
      riskLevel: null,
      findings: controller.signal.aborted
        ? 'Сервис не ответил вовремя. Повторите проверку.'
        : error instanceof TypeError
          ? 'Не удалось связаться с сервером проверки. Повторите попытку.'
          : error.message || 'Не удалось завершить проверку.',
    });
  } finally {
    clearTimeout(timer);
  }
  return record;
}

/**
 * Run person checks for people found on a company card.
 * @param {{inn: string, name: string, roles: string[]}[]} people
 * @returns {Promise<object[]>} completed records
 */
export async function checkPersonsFromCompany(people, options = {}) {
  return Promise.all(people.map(async (p) => {
    const record = {
      id: `person-auto-${p.inn}-${Date.now()}`,
      name: p.name,
      inn: p.inn,
      roles: p.roles,
      role: p.roles.join(', '),
      auto: true,
      requestedAt: new Date().toISOString().split('T')[0],
      status: 'Проверяется',
      findings: null,
      riskLevel: null,
    };
    return completePersonCheck(record, options);
  }));
}

/** Coverage summary for related people, e.g. «Проверено 5 из 8; ещё 3 не проверены». */
export function personCoverageSummary(people) {
  const list = people || [];
  const total = list.length;
  const done = list.filter(p => p.checkStatus === 'done').length;
  const errors = list.filter(p => p.checkStatus === 'error').length;
  const noInn = list.filter(p => p.checkStatus === 'no_inn').length;
  const pending = list.filter(p => p.checkStatus === 'not_checked' || p.checkStatus === 'checking').length;
  const checkable = list.filter(p => p.inn).length;
  return {
    total,
    checkable,
    done,
    errors,
    noInn,
    pending,
    text: total
      ? `Проверено ${done} из ${total}${pending ? `; ещё ${pending} не проверены` : ''}${errors ? `; с ошибкой: ${errors}` : ''}${noInn ? `; без ИНН: ${noInn}` : ''}`
      : 'Связанные люди не найдены',
  };
}
