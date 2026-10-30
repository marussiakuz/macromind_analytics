
export function renderCalibrationQuiz() {
  return `
    <div id="calibration-quiz-block" class="mb-8 slide-up" style="animation-delay: 0.02s">
      <div class="rounded-2xl p-[2px] shadow-soft" style="background: linear-gradient(135deg, #4D966F, #3D7D5C, #2D5E45);">
        <div class="bg-white rounded-[14px] p-6 sm:p-8">
          <div class="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-4">
              <div class="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl flex items-center justify-center">
                <i data-lucide="zap" class="w-6 h-6 text-white"></i>
              </div>
              <h2 class="text-lg sm:text-xl font-semibold text-gray-900">После загрузки документов сверьте информацию и направьте заявку в фонд.</h2>
            </div>
            <button type="button" id="polygon-start-btn" class="btn-primary inline-flex items-center justify-center gap-2 px-6 py-3 bg-primary hover:bg-primary-hover text-white font-medium rounded-xl shadow-soft transition-all whitespace-nowrap">
              <span>Продолжить</span>
              <i data-lucide="arrow-right" class="w-5 h-5"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}
