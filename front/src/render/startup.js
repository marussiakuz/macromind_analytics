import { getDocumentChecklist } from '../data/mockData.js';
import { state } from '../state.js';
import { renderHeader } from './header.js';
import { renderNotificationsHTML } from '../notifications.js';
import { renderCalibrationQuiz } from './calibrationQuiz.js';

export function renderStartupDashboard() {
  const documentChecklist = getDocumentChecklist(state.hasLegalEntity);
  const uploadedDocs = state.uploadedDocuments.length;
  const totalDocs = documentChecklist.length;
  const progress = totalDocs > 0 ? Math.round((uploadedDocs / totalDocs) * 100) : 0;

  const checklistHtml = documentChecklist
    .map((doc, index) => {
      const isUploaded = state.uploadedDocuments.includes(doc.id);
      return `
        <div class="stagger-item flex items-center justify-between p-4 border border-gray-100 rounded-xl hover:border-primary/40 transition-all" style="animation-delay: ${index * 0.05}s">
          <div class="flex items-center gap-4 min-w-0 flex-1">
            <div class="w-10 h-10 shrink-0 rounded-full flex items-center justify-center ${isUploaded ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'}">
              ${isUploaded ? '<i data-lucide="check" class="w-5 h-5"></i>' : `<span class="text-sm font-medium">${index + 1}</span>`}
            </div>
            <div class="min-w-0">
              <div class="font-medium text-gray-900">${doc.name}${doc.required ? '<span class="text-red-500 font-semibold">*</span>' : ''}</div>
              <div class="text-sm text-gray-500">${doc.description} • ${doc.format}</div>
            </div>
          </div>
          <div class="flex items-center gap-3 shrink-0 ml-2">
            ${
              isUploaded
                ? '<span class="px-3 py-1 bg-green-100 text-green-700 text-sm rounded-full font-medium">Загружено</span>'
                : `<button type="button" class="upload-btn btn-primary px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm rounded-lg font-medium" data-doc-id="${doc.id}">Загрузить</button>`
            }
          </div>
        </div>
      `;
    })
    .join('');

  return `
    <div class="min-h-screen bg-gray-50">
      ${renderHeader()}
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        ${renderCalibrationQuiz()}

        <div class="bg-white rounded-2xl shadow-soft p-8 mb-8 slide-up" style="animation-delay: 0s">
          <h2 class="text-xl font-semibold text-gray-900 mb-6 flex items-center gap-2">
            <i data-lucide="activity" class="w-5 h-5 text-primary"></i>
            Статус заявки
          </h2>
          <div class="flex items-center">
            <div class="flex flex-col items-center">
              <div class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center">
                <i data-lucide="check" class="w-5 h-5"></i>
              </div>
              <span class="mt-2 text-sm font-semibold text-primary">Подано</span>
            </div>
            <div class="flex-1 h-0.5 bg-primary mx-3"></div>
            <div class="flex flex-col items-center">
              <div class="w-10 h-10 rounded-full border-2 border-gray-200 bg-gray-50 text-gray-400 flex items-center justify-center text-sm font-medium">2</div>
              <span class="mt-2 text-sm font-medium text-gray-400">Проверка</span>
            </div>
            <div class="flex-1 h-0.5 bg-gray-200 mx-3"></div>
            <div class="flex flex-col items-center">
              <div class="w-10 h-10 rounded-full border-2 border-gray-200 bg-gray-50 text-gray-400 flex items-center justify-center text-sm font-medium">3</div>
              <span class="mt-2 text-sm font-medium text-gray-400">Решение ИК</span>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-soft p-8 mb-8 slide-up" style="animation-delay: 0.05s">
          <h2 class="text-xl font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <i data-lucide="upload-cloud" class="w-5 h-5 text-secondary"></i>
            Загрузка питч-дека<span class="text-red-500 font-semibold">*</span>
          </h2>
          <div id="pitch-deck-upload" class="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-primary transition-colors cursor-pointer">
            <i data-lucide="file-text" class="w-12 h-12 text-gray-300 mx-auto mb-4"></i>
            <p class="text-gray-900 font-medium mb-2">Перетащите файл сюда или нажмите для загрузки</p>
            <p class="text-sm text-gray-500">PPTX, PDF, DOCX до 50MB</p>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-soft p-8 slide-up" style="animation-delay: 0.1s">
          <h2 class="text-xl font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <i data-lucide="clipboard-list" class="w-5 h-5 text-primary"></i>
            Чек-лист документов
          </h2>
          <p class="text-sm text-gray-500 mb-4">Укажите, зарегистрировано ли юридическое лицо — от этого зависит список обязательных документов.</p>
          <div class="flex flex-col sm:flex-row sm:items-center gap-3 mb-6 p-4 bg-gray-50 rounded-xl">
            <span class="text-sm font-medium text-gray-700 shrink-0">Юридическое лицо</span>
            <div class="flex rounded-xl border border-gray-200 p-1 bg-white w-full sm:w-auto">
              <button type="button" id="legal-entity-yes" class="legal-entity-toggle flex-1 sm:flex-none px-6 py-2 rounded-lg text-sm font-medium transition-all ${state.hasLegalEntity ? 'bg-primary text-white shadow-sm' : 'text-gray-500 hover:text-gray-900'}">
                Есть
              </button>
              <button type="button" id="legal-entity-no" class="legal-entity-toggle flex-1 sm:flex-none px-6 py-2 rounded-lg text-sm font-medium transition-all ${!state.hasLegalEntity ? 'bg-primary text-white shadow-sm' : 'text-gray-500 hover:text-gray-900'}">
                Нет
              </button>
            </div>
          </div>
          <div class="space-y-3">
            ${checklistHtml}
          </div>
        </div>
      </div>
      ${renderNotificationsHTML()}
    </div>
  `;
}
