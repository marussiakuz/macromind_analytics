export function generateId() {
  return 'id-' + Math.random().toString(36).slice(2, 11);
}

export function formatDate(dateStr) {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function getStatusColor(status) {
  const colors = {
    'Заявка принята': 'bg-primary/[.18] text-primary',
    'На анализе': 'bg-amber-900/[.35] text-amber-400',
    'Решение ИК': 'bg-purple-900/[.35] text-purple-400',
    Результат: 'bg-green-900/[.35] text-green-400',
  };
  return colors[status] || 'bg-[#383838] text-text-secondary';
}

export function getRiskColor(severity) {
  const colors = {
    high: 'bg-red-900/[.30] text-red-400 border-red-800/50',
    medium: 'bg-amber-900/[.30] text-amber-400 border-amber-700/50',
    low: 'bg-green-900/[.30] text-green-400 border-green-700/50',
  };
  return colors[severity] || 'bg-[#383838] text-text-secondary';
}

export function getRiskIcon(severity) {
  const icons = { high: '🔴', medium: '🟡', low: '🟢' };
  return icons[severity] || '⚪';
}

export function getVerificationBadge(verification) {
  const badges = {
    confirmed:
      '<span class="inline-flex items-center gap-1 px-2 py-1 bg-green-900/[.35] text-green-400 text-xs rounded-full"><i data-lucide="check" class="w-3 h-3"></i>Подтверждено</span>',
    from_applicant:
      '<span class="inline-flex items-center gap-1 px-2 py-1 bg-primary/[.18] text-primary text-xs rounded-full"><i data-lucide="info" class="w-3 h-3"></i>От заявителя</span>',
    unconfirmed:
      '<span class="inline-flex items-center gap-1 px-2 py-1 bg-red-900/[.35] text-red-400 text-xs rounded-full"><i data-lucide="alert-triangle" class="w-3 h-3"></i>Не подтверждено</span>',
  };
  return badges[verification] || '';
}

export function renderContentWithCitations(content) {
  return content.replace(
    /\[(\d+)\]/g,
    '<sup class="text-primary cursor-pointer hover:underline" data-citation="$1">[$1]</sup>'
  );
}

export function getRiskCategoryLabel(category) {
  const labels = {
    legal: 'Юридический',
    domain: 'Домен',
    financial: 'Финансовый',
    team: 'Команда',
    technology: 'Технологический',
    resource: 'Ресурсный (сырье)',
    personnel: 'Кадровый',
    regulatory: 'Регуляторный',
    infrastructure: 'Инфраструктурный',
    equipment: 'Оборудование',
  };
  return labels[category] || category;
}
