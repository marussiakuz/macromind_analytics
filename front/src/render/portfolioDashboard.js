import { portfolioAlerts } from '../data/mockData.js';

function alertBadgeClass(color) {
  const map = {
    red: 'bg-red-900/[.30] text-red-400',
    amber: 'bg-amber-900/[.30] text-amber-400',
    orange: 'bg-orange-900/[.30] text-orange-400',
  };
  return map[color] ?? 'bg-primary/[.18] text-primary';
}

function deadlineTextClass(color) {
  const map = { red: 'text-red-400', amber: 'text-amber-400', orange: 'text-orange-400' };
  return map[color] ?? 'text-text-secondary';
}

export function renderPortfolioDashboard() {
  return `
    <div class="flex-1 flex flex-col gap-6 slide-up">
      <!-- Stats row -->
      <div class="grid grid-cols-4 gap-4">
        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <p class="text-text-secondary text-sm">Всего компаний</p>
              <h3 class="text-2xl font-bold text-text-main mt-1">4</h3>
            </div>
            <div class="p-2 bg-primary/[.18] rounded-xl">
              <i data-lucide="briefcase" class="w-5 h-5 text-primary"></i>
            </div>
          </div>
          <div class="text-xs text-text-secondary">+1 новая в этом квартале</div>
        </div>

        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <p class="text-text-secondary text-sm">Ближайшие дедлайны</p>
              <h3 class="text-2xl font-bold text-amber-400 mt-1">5</h3>
            </div>
            <div class="p-2 bg-amber-900/[.30] rounded-xl">
              <i data-lucide="clock" class="w-5 h-5 text-amber-400"></i>
            </div>
          </div>
          <div class="text-xs text-text-secondary">Отчёты для LP до 15 мая</div>
        </div>

        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <p class="text-text-secondary text-sm">Судебные риски</p>
              <h3 class="text-2xl font-bold text-red-400 mt-1">2</h3>
            </div>
            <div class="p-2 bg-red-900/[.30] rounded-xl">
              <i data-lucide="gavel" class="w-5 h-5 text-red-400"></i>
            </div>
          </div>
          <div class="text-xs text-text-secondary">Новые иски к портфельным компаниям</div>
        </div>

        <div class="bg-card rounded-2xl shadow-soft p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <p class="text-text-secondary text-sm">Истекают полномочия CEO</p>
              <h3 class="text-2xl font-bold text-text-main mt-1">3</h3>
            </div>
            <div class="p-2 bg-[#3a3a3a] rounded-xl">
              <i data-lucide="user-x" class="w-5 h-5 text-text-secondary"></i>
            </div>
          </div>
          <div class="text-xs text-text-secondary">Требуется продление или замена</div>
        </div>
      </div>

      <!-- Alerts + Right column -->
      <div class="grid grid-cols-3 gap-6">
        <!-- Alerts -->
        <div class="col-span-2 bg-card rounded-2xl shadow-soft overflow-hidden">
          <div class="px-6 py-4 border-b border-card-border flex justify-between items-center bg-red-900/[.10]">
            <h2 class="font-semibold text-text-main flex items-center gap-2">
              <i data-lucide="alert-triangle" class="w-5 h-5 text-red-400"></i>
              Требует внимания (КадАрбитр / SPARK / ФНС)
            </h2>
            <button class="text-xs text-primary font-medium hover:underline">Обновить данные</button>
          </div>
          <div class="divide-y divide-card-border">
            ${portfolioAlerts.map(alert => `
              <div class="p-6 flex items-start gap-4 hover:bg-[#333] transition-colors cursor-pointer">
                <div class="mt-1 w-44 shrink-0">
                  <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${alertBadgeClass(alert.typeColor)}">
                    ${alert.type}
                  </span>
                </div>
                <div class="flex-1">
                  <h4 class="text-sm font-semibold text-text-main">${alert.title}</h4>
                  <p class="text-sm text-text-secondary mt-1">${alert.description}</p>
                  <div class="mt-3 flex items-center gap-4 text-xs text-text-secondary">
                    <span class="flex items-center gap-1">
                      <i data-lucide="database" class="w-3 h-3"></i> Источник: ${alert.source}
                    </span>
                    <span class="flex items-center gap-1 ${deadlineTextClass(alert.deadlineColor)} font-medium">
                      <i data-lucide="timer" class="w-3 h-3"></i> ${alert.deadlineLabel}
                    </span>
                  </div>
                </div>
                <button class="px-3 py-1.5 bg-surface border border-card-border text-text-main text-xs font-medium rounded-lg hover:bg-[#333] whitespace-nowrap shrink-0 transition-all">
                  ${alert.action}
                </button>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Right column -->
        <div class="flex flex-col gap-6">
          <!-- Upcoming events -->
          <div class="bg-card rounded-2xl shadow-soft p-6">
            <h3 class="font-semibold text-text-main mb-4 flex items-center gap-2">
              <i data-lucide="calendar" class="w-4 h-4 text-primary"></i>
              Ближайшие события
            </h3>
            <div class="space-y-4">
              <div class="flex gap-3 items-start pb-4 border-b border-card-border">
                <div class="flex flex-col items-center min-w-[40px]">
                  <span class="text-xs font-bold text-text-secondary">МАЙ</span>
                  <span class="text-lg font-bold text-text-main">15</span>
                </div>
                <div>
                  <p class="text-sm font-medium text-text-main">Отправка Q1 отчётов LP</p>
                  <p class="text-xs text-text-secondary">Investment Partnership I</p>
                </div>
              </div>
              <div class="flex gap-3 items-start pb-4 border-b border-card-border">
                <div class="flex flex-col items-center min-w-[40px]">
                  <span class="text-xs font-bold text-text-secondary">МАЙ</span>
                  <span class="text-lg font-bold text-text-main">20</span>
                </div>
                <div>
                  <p class="text-sm font-medium text-text-main">Заседание Инвесткома</p>
                  <p class="text-xs text-text-secondary">Обсуждение Series B для «СтартапХ»</p>
                </div>
              </div>
              <div class="flex gap-3 items-start">
                <div class="flex flex-col items-center min-w-[40px]">
                  <span class="text-xs font-bold text-text-secondary">ИЮН</span>
                  <span class="text-lg font-bold text-text-main">05</span>
                </div>
                <div>
                  <p class="text-sm font-medium text-text-main">Продление CEO АО «ФинТех»</p>
                  <p class="text-xs text-text-secondary">Подготовка протокола ОСА</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Activity log -->
          <div class="bg-card rounded-2xl shadow-soft p-6">
            <h3 class="font-semibold text-text-main mb-4 flex items-center gap-2">
              <i data-lucide="activity" class="w-4 h-4 text-primary"></i>
              Активность команды
            </h3>
            <div class="space-y-4">
              <div class="flex gap-3 items-start">
                <div class="w-8 h-8 rounded-full bg-blue-900/[.40] flex items-center justify-center text-blue-400 text-xs font-bold shrink-0">ЕП</div>
                <div>
                  <p class="text-sm text-text-main"><span class="font-medium">Елена П.</span> загрузила новую финмодель</p>
                  <p class="text-xs text-text-secondary">ООО «СтартапХ» · 2 часа назад</p>
                </div>
              </div>
              <div class="flex gap-3 items-start">
                <div class="w-8 h-8 rounded-full bg-purple-900/[.40] flex items-center justify-center text-purple-400 text-xs font-bold shrink-0">ИС</div>
                <div>
                  <p class="text-sm text-text-main"><span class="font-medium">Иван С.</span> согласовал договор займа</p>
                  <p class="text-xs text-text-secondary">АО «ФинТех» · Вчера</p>
                </div>
              </div>
              <div class="flex gap-3 items-start">
                <div class="w-8 h-8 rounded-full bg-primary/[.18] flex items-center justify-center text-primary text-xs font-bold shrink-0">AI</div>
                <div>
                  <p class="text-sm text-text-main"><span class="font-medium">VentureBot</span> обнаружил новый иск</p>
                  <p class="text-xs text-text-secondary">КадАрбитр · Вчера</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
