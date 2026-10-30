import { state } from '../state.js';

export function renderHeader() {
  const isStartup = state.currentRole === 'startup';
  const header   = isStartup ? 'bg-white/90 backdrop-blur-md border-b border-gray-100' : 'bg-[#1A1A1A]/95 backdrop-blur-md border-b border-card-border';
  const title    = isStartup ? 'text-gray-900' : 'text-text-main';
  const muted    = isStartup ? 'text-gray-500 hover:text-gray-900' : 'text-text-secondary hover:text-text-main';
  const divider  = isStartup ? 'border-gray-100' : 'border-card-border';
  const ring     = isStartup ? 'ring-black/[0.06]' : 'ring-white/[0.08]';

  const logoSection = isStartup
    ? `<div class="flex items-center gap-2.5 min-w-0">`
    : `<div class="w-64 shrink-0 flex items-center gap-2.5 px-6 border-r ${divider}">`;

  const innerWrapper = isStartup
    ? `<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8"><div class="flex items-center justify-between h-16">`
    : `<div class="flex items-center justify-between h-16 w-full">`;

  const innerWrapperClose = isStartup ? `</div></div>` : `</div>`;

  const rightPadding = isStartup ? '' : 'px-6 sm:px-8 lg:px-10';

  return `
    <header class="${header} sticky top-0 z-40">
      ${innerWrapper}
        ${logoSection}
          <img
            src="/logo-macromind.png"
            alt=""
            width="36"
            height="36"
            class="h-8 w-8 sm:h-9 sm:w-9 shrink-0 rounded-lg object-contain shadow-sm ring-1 ${ring}"
            decoding="async"
          />
          <span class="text-lg font-semibold ${title} truncate">MacroMindAnalytics</span>
        </div>
        <div class="flex items-center gap-4 ${rightPadding}">
          <button id="switch-role" type="button" class="px-4 py-2 text-sm ${muted} transition-colors">
            <i data-lucide="repeat" class="w-4 h-4 inline mr-1"></i>
            ${isStartup ? 'Переключиться на Фонд' : 'Переключиться на Стартап'}
          </button>
          <div class="flex items-center gap-3 pl-4 border-l ${divider}">
            <div class="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white text-sm font-medium">
              ${isStartup ? 'С' : 'Ф'}
            </div>
            <button id="logout" type="button" class="text-sm ${muted} transition-colors">
              <i data-lucide="log-out" class="w-4 h-4"></i>
            </button>
          </div>
        </div>
      ${innerWrapperClose}
    </header>
  `;
}
