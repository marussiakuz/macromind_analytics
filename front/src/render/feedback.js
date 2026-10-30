import { state } from '../state.js';

export function renderFeedbackModal() {
  if (!state.showFeedbackModal) return '';

  return `
    <div id="feedback-modal" class="fixed inset-0 modal-overlay bg-black/40 z-50 flex items-center justify-center p-4">
      <div class="bg-card rounded-2xl shadow-large w-full max-w-lg slide-up">
        <div class="p-6 border-b border-card-border">
          <h3 class="text-xl font-semibold text-text-main">Ответ стартапу</h3>
          <p class="text-sm text-text-secondary mt-1">Отправьте фидбек основателям проекта</p>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium text-text-main mb-2">Решение</label>
            <div class="flex gap-3">
              <label class="flex items-center gap-2 px-4 py-3 border border-green-700/50 bg-green-900/[.20] rounded-xl cursor-pointer hover:bg-green-900/30 transition-colors">
                <input type="radio" name="decision" value="pass" class="text-green-400">
                <span class="text-sm font-medium text-green-400">✅ Переход на следующий этап</span>
              </label>
              <label class="flex items-center gap-2 px-4 py-3 border border-red-800/50 bg-red-900/[.20] rounded-xl cursor-pointer hover:bg-red-900/30 transition-colors">
                <input type="radio" name="decision" value="reject" class="text-red-400">
                <span class="text-sm font-medium text-red-400">❌ Отказ</span>
              </label>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-text-main mb-2">Комментарий</label>
            <textarea id="feedback-text" class="input-field w-full px-4 py-3 rounded-xl focus:outline-none resize-none" rows="4" placeholder="Опишите решение и рекомендации для стартапа..."></textarea>
          </div>
          <div class="flex items-center gap-2 p-3 bg-[#222222] rounded-xl">
            <i data-lucide="sparkles" class="w-4 h-4 text-secondary"></i>
            <button type="button" id="ai-generate" class="text-sm text-secondary hover:underline">Сгенерировать ответ с AI</button>
          </div>
        </div>
        <div class="p-6 border-t border-card-border flex justify-end gap-3">
          <button type="button" id="cancel-feedback" class="px-4 py-2 text-text-secondary hover:text-text-main transition-colors">Отмена</button>
          <button type="button" id="send-feedback-btn" class="btn-primary px-6 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium">Отправить</button>
        </div>
      </div>
    </div>
  `;
}
