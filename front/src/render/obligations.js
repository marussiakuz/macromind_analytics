import { lpObligations } from '../data/mockData.js';

function statusBadge(status) {
  const map = {
    ready: 'bg-green-900/[.30] text-green-400',
    overdue: 'bg-red-900/[.30] text-red-400',
    in_progress: 'bg-amber-900/[.30] text-amber-400',
    planned: 'bg-primary/[.18] text-primary',
  };
  return map[status] ?? 'bg-primary/[.18] text-primary';
}

export function renderObligations() {
  return `
    <div class="flex-1 flex flex-col gap-6 slide-up">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-text-main mb-2">Обязательства перед LP</h1>
          <p class="text-text-secondary">Календарь отчётности и уведомлений</p>
        </div>
        <div class="flex gap-2">
          <button class="inline-flex items-center gap-2 px-4 py-2 bg-card border border-card-border rounded-xl text-sm font-medium text-text-main hover:bg-[#333] transition-all shadow-soft">
            <i data-lucide="download" class="w-4 h-4 shrink-0 text-text-secondary"></i>
            Экспорт в Excel
          </button>
          <button class="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm font-medium rounded-xl transition-all shadow-soft">
            <i data-lucide="plus" class="w-4 h-4 shrink-0"></i>
            Добавить обязательство
          </button>
        </div>
      </div>

      <div class="bg-card rounded-2xl shadow-soft overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="bg-surface">
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Тип отчёта</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Компания / Фонд</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Срок сдачи</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Статус</th>
                <th class="text-left text-sm font-medium text-text-secondary px-6 py-4">Действие</th>
              </tr>
            </thead>
            <tbody>
              ${lpObligations.map((ob, i) => `
                <tr class="border-t border-card-border hover:bg-[#333] transition-colors" style="animation-delay: ${i * 0.05}s">
                  <td class="px-6 py-4 font-medium text-text-main">${ob.type}</td>
                  <td class="px-6 py-4 text-text-secondary">${ob.entity}</td>
                  <td class="px-6 py-4 ${ob.status === 'overdue' ? 'text-red-400 font-medium' : 'text-text-main'}">${ob.deadline}</td>
                  <td class="px-6 py-4">
                    <span class="px-3 py-1 rounded-full text-xs font-medium ${statusBadge(ob.status)}">${ob.statusLabel}</span>
                  </td>
                  <td class="px-6 py-4">
                    <button class="text-primary hover:underline text-sm font-medium">${ob.action}</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}
