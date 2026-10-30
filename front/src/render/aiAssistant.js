export function renderAiAssistant() {
  return `
    <div class="flex-1 flex flex-col slide-up" style="min-height: 0">
      <div class="bg-card rounded-2xl shadow-soft flex flex-col overflow-hidden" style="height: calc(100vh - 220px)">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-card-border bg-[#252525] flex justify-between items-center shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 bg-primary/[.18] rounded-full flex items-center justify-center text-primary shrink-0">
              <i data-lucide="sparkles" class="w-4 h-4"></i>
            </div>
            <div>
              <h3 class="font-semibold text-text-main">VentureBot</h3>
              <p class="text-xs text-text-secondary">AI-ассистент MacroMindAnalytics</p>
            </div>
          </div>
          <div class="flex gap-2">
            <span class="text-xs px-2 py-1 bg-surface border border-card-border rounded-lg text-text-secondary">Контекст: Портфель</span>
            <span class="text-xs px-2 py-1 bg-surface border border-card-border rounded-lg text-text-secondary">Источник: Внутр. + SPARK</span>
          </div>
        </div>

        <!-- Messages -->
        <div class="flex-1 p-6 overflow-y-auto space-y-4" id="chat-messages">
          <!-- Bot opening message -->
          <div class="flex gap-3">
            <div class="w-9 h-9 bg-primary rounded-full flex-shrink-0 flex items-center justify-center text-white">
              <i data-lucide="bot" class="w-4 h-4"></i>
            </div>
            <div class="bg-[#333] p-4 rounded-2xl rounded-tl-none border border-card-border max-w-2xl">
              <p class="text-sm text-text-main leading-relaxed">
                Добро пожаловать! Я проанализировал текущее состояние портфельных компаний.<br><br>
                На сегодня есть <strong class="text-text-main">2 критических события</strong>:<br>
                1. Иск к BioTech Solutions — требуется уведомление LP до 17.05.<br>
                2. Истечение полномочий CEO в АО «ФинТех Солюшнс».<br><br>
                Хотите, я подготовлю черновик уведомления для партнёров?
              </p>
            </div>
          </div>

          <!-- User message -->
          <div class="flex gap-3 flex-row-reverse">
            <div class="w-9 h-9 bg-[#444] rounded-full flex-shrink-0 flex items-center justify-center text-text-secondary">
              <span class="text-xs font-bold">ЮО</span>
            </div>
            <div class="bg-primary text-white p-4 rounded-2xl rounded-tr-none max-w-2xl">
              <p class="text-sm leading-relaxed">
                Да, подготовь проект письма по иску. Используй шаблон «Уведомление о судебном споре».
              </p>
            </div>
          </div>

          <!-- Bot response with document draft -->
          <div class="flex gap-3">
            <div class="w-9 h-9 bg-primary rounded-full flex-shrink-0 flex items-center justify-center text-white">
              <i data-lucide="bot" class="w-4 h-4"></i>
            </div>
            <div class="bg-[#333] p-4 rounded-2xl rounded-tl-none border border-card-border max-w-3xl w-full">
              <div class="flex justify-between items-center mb-3 pb-2 border-b border-card-border">
                <span class="text-xs font-semibold text-text-secondary uppercase tracking-wider">Черновик документа</span>
                <button class="text-xs text-primary flex items-center gap-1 hover:underline">
                  <i data-lucide="download" class="w-3 h-3"></i> Скачать DOCX
                </button>
              </div>
              <div class="bg-surface p-4 rounded-xl border border-card-border font-mono text-xs text-text-secondary whitespace-pre-wrap leading-relaxed">Уважаемые партнёры,

В соответствии с п. 4.2 Договора инвестиционного товарищества №1, уведомляем Вас о возникновении судебного спора в отношении портфельной компании BioTech Solutions.

Детали:
  — Истец: ИП Пупкин
  — Сумма иска: 500 000 руб.
  — Статус: Принят к производству (03.05.2026)

Мы оцениваем риски как умеренные и держим ситуацию на контроле.

С уважением,
MacroMindAnalytics</div>
            </div>
          </div>
        </div>

        <!-- Input area -->
        <div class="p-4 bg-card border-t border-card-border shrink-0">
          <div class="relative">
            <input
              type="text"
              id="chat-input"
              placeholder="Задайте вопрос или попросите создать документ..."
              class="w-full pl-4 pr-12 py-3 bg-surface border border-card-border rounded-xl focus:outline-none focus:border-primary text-text-main text-sm placeholder:text-text-secondary transition-all"
            >
            <button id="chat-send-btn" class="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors">
              <i data-lucide="send" class="w-4 h-4"></i>
            </button>
          </div>
          <div class="flex gap-2 mt-2">
            <button class="chat-quick-cmd text-xs px-3 py-1.5 bg-surface border border-card-border text-text-secondary rounded-lg hover:text-text-main hover:border-primary/[.50] transition-all">Проверить сроки</button>
            <button class="chat-quick-cmd text-xs px-3 py-1.5 bg-surface border border-card-border text-text-secondary rounded-lg hover:text-text-main hover:border-primary/[.50] transition-all">Сводка по рискам</button>
            <button class="chat-quick-cmd text-xs px-3 py-1.5 bg-surface border border-card-border text-text-secondary rounded-lg hover:text-text-main hover:border-primary/[.50] transition-all">Особые мнения Инвесткома</button>
          </div>
        </div>
      </div>
    </div>
  `;
}
