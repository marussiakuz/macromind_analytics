export const riskLabels = {
  unreliable_address: 'Недостоверный юридический адрес',
  disqualified_management: 'Дисквалифицированные руководители',
  mass_director: 'Массовый руководитель',
  mass_founder: 'Массовый учредитель',
  unfair_supplier: 'Реестр недобросовестных поставщиков',
  illegal_financial_activity: 'Нелегальная финансовая деятельность',
  sanctioned: 'Санкции в отношении компании',
  sanctioned_founder: 'Санкции в отношении учредителя',
};

/** Complete the same history record on success, failure or timeout. */
export async function completeCompanyCheck(record, {
  apiBase = 'http://localhost:8000',
  fetchImpl = globalThis.fetch,
  timeoutMs = 35000,
} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(
      `${apiBase}/api/v1/counterparties/${encodeURIComponent(record.inn)}`,
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
    const company = data.company;
    if (!company || company.inn !== record.inn || !company.name) {
      throw new Error('В ответе нет данных запрошенной компании. Повторите проверку.');
    }
    const risks = Object.entries(company.risk_factors || {})
      .filter(([, value]) => value === true)
      .map(([key]) => riskLabels[key] || key);
    const summary = [];
    if (company.status) summary.push(`Статус: ${company.status}`);
    if (company.registration_date) summary.push(`Дата регистрации: ${company.registration_date}`);
    if (company.director) summary.push(`Руководитель: ${company.director}`);
    if (company.address) summary.push(`Адрес: ${company.address}`);
    if (risks.length) summary.push(`Факторы риска: ${risks.join('; ')}`);
    else summary.push('В полученных сведениях нет отмеченных факторов риска. Полная оценка надёжности не запрашивалась.');
    Object.assign(record, {
      name: company.name,
      status: 'Анализ завершен',
      company,
      source: data.source || 'checko',
      findings: summary.join('\n'),
      // Absence of reported factors is not a completed reliability assessment.
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
