/** Recognize the supported report structure independently of its storage version. */
export function hasEvidenceReport(summary) {
  const report = summary?.analytical_report;
  if (!report || !Array.isArray(report.sources) || !report.sections
      || typeof report.sections !== 'object' || Array.isArray(report.sections)) return false;
  if (Object.keys(report.sections).length === 0 && (summary.research_schema_version || report._meta?.schema_version)) return true;
  return ['world', 'russia', 'trends', 'market_risks', 'technology_risks']
    .some(key => Array.isArray(report.sections[key]));
}

/** Stage A/C: multi-direction profile is present and readable. */
export function hasCompanyDirections(summary) {
  const report = summary?.analytical_report;
  const directions = report?.company?.directions
    || summary?.company_research?.directions
    || summary?.market_scope?.directions;
  return Array.isArray(directions) && directions.length > 0;
}

/** Stage B: relation-classified competitor table (suppliers separated). */
export function hasRelationCompetitors(summary) {
  const report = summary?.analytical_report;
  const comps = report?.competitors || {};
  return Array.isArray(comps.suppliers_partners)
    || Array.isArray(comps.rejected)
    || (comps.russia || []).some?.(r => r?.relation_class)
    || (comps.world || []).some?.(r => r?.relation_class);
}

export function getDirections(summary) {
  return summary?.analytical_report?.company?.directions
    || summary?.company_research?.directions
    || summary?.market_scope?.directions
    || [];
}


/** Empty reports caused by a service failure must not freeze the saved result. */
export function hasFailedResearch(summary) {
  const sections = summary?.analytical_report?.sections || {};
  if (Object.values(sections).some(rows => Array.isArray(rows) && rows.length)) return false;
  return (summary?.errors || []).length > 0
    || (summary?.limitations || []).some(text => /нет связи|не ответила вовремя|не ответил вовремя|HTTP (?:4|5)\d\d/i.test(String(text)));
}
