import { state } from '../state.js';

export function renderLoginPage() {
  const isStartup = state.currentRole === 'startup';

  // ── theme tokens ────────────────────────────────────────────────
  const pageBg    = isStartup
    ? 'bg-gradient-to-br from-gray-50 via-white to-primary-light/20'
    : 'bg-gradient-to-br from-surface via-[#1A1A1A] to-primary-light';
  const cardBg    = isStartup ? 'bg-white'        : 'bg-card';
  const tabBar    = isStartup ? 'bg-gray-100'     : 'bg-[#222222]';
  const demoBg    = isStartup ? 'bg-gray-50'      : 'bg-[#222222]';
  const titleCol  = isStartup ? 'text-gray-900'   : 'text-text-main';
  const subtleCol = isStartup ? 'text-gray-500'   : 'text-text-secondary';
  const labelCol  = isStartup ? 'text-gray-700'   : 'text-text-main';
  const footerCol = isStartup ? 'text-gray-400'   : 'text-text-light';
  const inputCls  = isStartup
    ? 'w-full px-4 py-3 bg-white border border-gray-200 text-gray-500 placeholder-gray-300 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/60 focus:border-primary/50 transition-all'
    : 'input-field w-full px-4 py-3 border border-[#484848] rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/60 focus:border-primary/50 transition-all';
  const modalBg   = isStartup ? 'bg-white border border-gray-100' : 'bg-card border border-card-border';
  const modalClose = isStartup ? 'text-gray-400 hover:bg-gray-100 hover:text-gray-700' : 'text-text-secondary hover:bg-[#222222] hover:text-text-main';

  const tabStartup = state.currentRole === 'startup'
    ? (isStartup ? 'bg-white shadow text-primary' : 'bg-card shadow text-primary')
    : (isStartup ? 'text-gray-500 hover:text-gray-900' : 'text-text-secondary hover:text-text-main');
  const tabFund = state.currentRole === 'fund'
    ? (isStartup ? 'bg-white shadow text-secondary' : 'bg-card shadow text-secondary')
    : (isStartup ? 'text-gray-500 hover:text-gray-900' : 'text-text-secondary hover:text-text-main');

  return `
    <div class="min-h-screen flex items-center justify-center ${pageBg}">
      <div class="w-full max-w-md p-8">
        <div class="text-center mb-8 slide-up">
          <h1 class="text-3xl font-semibold ${titleCol} mb-2">MacroMindAnalytics</h1>
          <p class="${subtleCol}">Платформа автоматизации Due Diligence</p>
        </div>
        <div class="${cardBg} rounded-2xl shadow-soft p-8 slide-up" style="animation-delay: 0.1s">
          <div class="flex gap-2 mb-6 p-1 ${tabBar} rounded-xl">
            <button type="button" id="role-startup" class="flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${tabStartup}">
              <i data-lucide="rocket" class="w-4 h-4 inline mr-2"></i>Стартап
            </button>
            <button type="button" id="role-fund" class="flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all ${tabFund}">
              <i data-lucide="briefcase" class="w-4 h-4 inline mr-2"></i>Фонд
            </button>
          </div>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium ${labelCol} mb-2">Email</label>
              <input type="email" id="login-email" value="demo@macromind.ai" class="${inputCls}" placeholder="name@company.com">
            </div>
            <div>
              <label class="block text-sm font-medium ${labelCol} mb-2">Пароль</label>
              <input type="password" id="login-password" value="demo123" class="${inputCls}" placeholder="••••••••">
            </div>
            ${
              state.currentRole === 'startup'
                ? `
            <div class="flex items-start gap-3 pt-1">
              <input type="checkbox" id="ai-registry-consent" class="mt-1 h-4 w-4 shrink-0 rounded ${isStartup ? 'border-gray-300' : 'border-[#555555]'} text-primary focus:ring-primary focus:ring-offset-0 cursor-pointer" />
              <div class="text-sm ${subtleCol} leading-relaxed">
                <label for="ai-registry-consent" class="cursor-pointer">
                  Разрешаю ИИ-обработку данных реестров для авто-оценки рисков. Понимаю, что вывод влияет на решение о партнёрстве. Доступна ручная проверка.
                </label>
                <button type="button" id="ai-consent-info-btn" class="inline-flex items-center justify-center min-w-[1.5rem] text-primary font-semibold hover:underline ml-0.5 align-baseline" aria-label="Подробнее об ИИ-обработке">[?]</button>
              </div>
            </div>
            `
                : ''
            }
            <button type="button" id="login-btn" class="login-btn w-full py-3 px-4 bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary text-white font-medium rounded-xl transition-all shadow-soft" ${state.currentRole === 'startup' ? 'disabled' : ''}>
              Войти
            </button>
          </div>
          <div class="mt-6 p-4 ${demoBg} rounded-xl">
            <p class="text-xs ${subtleCol} text-center mb-2">Демо доступ</p>
            <div class="flex justify-center gap-4 text-xs">
              <span class="${titleCol}"><strong>Email:</strong> demo@macromind.ai</span>
              <span class="${titleCol}"><strong>Пароль:</strong> demo123</span>
            </div>
          </div>
          <div class="mt-6 text-center">
            <a href="#" class="text-sm text-primary hover:underline">Забыли пароль?</a>
          </div>
        </div>
        <div class="mt-8 text-center text-xs ${footerCol}">
          <p>© 2026 MacroMindAnalytics. Все права защищены.</p>
        </div>
      </div>
      ${
        state.showAiConsentModal
          ? `
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" id="ai-consent-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="ai-consent-modal-title">
        <div id="ai-consent-modal-panel" class="${modalBg} rounded-2xl shadow-soft max-w-md w-full p-6 relative slide-up">
          <h3 id="ai-consent-modal-title" class="text-lg font-semibold ${titleCol} mb-3 pr-8">ИИ-обработка данных</h3>
          <button type="button" id="ai-consent-modal-close-x" class="absolute top-4 right-4 p-2 rounded-lg ${modalClose} transition-colors" aria-label="Закрыть">
            <i data-lucide="x" class="w-5 h-5"></i>
          </button>
          <p class="text-sm ${subtleCol} leading-relaxed">
            Платформа использует ИИ для анализа данных из ЕГРЮЛ, судебных баз и иных открытых источников.
            Алгоритм формирует скоринговую оценку и рекомендации.
          </p>
          <button type="button" id="ai-consent-modal-ok" class="mt-6 w-full py-3 px-4 bg-primary hover:bg-primary-hover text-white font-medium rounded-xl transition-all shadow-soft">
            Понятно
          </button>
        </div>
      </div>
      `
          : ''
      }
    </div>
  `;
}
