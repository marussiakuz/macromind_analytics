import { state } from '../state.js';
import { showNotification } from '../notifications.js';

/**
 * Компонент «Компетенции» — поиск информации о людях.
 * Форма ввода → кандидаты → полный отчёт → PDF.
 */

const API_BASE = 'http://localhost:8001';

// ============================================================
// RENDER: Форма поиска
// ============================================================

export function renderCompetencyTab() {
  return `
    <div class="flex-1 flex flex-col">
      <!-- Заголовок -->
      <div class="mb-8 slide-up">
        <h1 class="text-2xl font-semibold text-text-main mb-2">Проверка компетенций</h1>
        <p class="text-text-secondary">Поиск информации о человеке по ФИО, никнеймам, навыкам и профессии</p>
      </div>

      <!-- Форма поиска -->
      <div class="bg-card rounded-2xl shadow-soft p-8 mb-8 slide-up" style="animation-delay: 0.1s">
        <h2 class="text-xl font-semibold text-text-main mb-6">Параметры поиска</h2>
        <form id="competency-search-form" class="space-y-5">

          <!-- Обязательные поля -->
          <div class="grid grid-cols-2 gap-4">
            <div class="col-span-2">
              <label class="block text-sm font-medium text-text-main mb-2">
                ФИО <span class="text-red-400">*</span>
              </label>
              <input type="text" id="comp-full-name"
                placeholder="Иванов Иван Иванович"
                class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all"
                required />
            </div>
          </div>

          <!-- Необязательные поля -->
          <div class="border-t border-card-border pt-5">
            <p class="text-xs text-text-secondary mb-4 uppercase tracking-wider font-medium">
              Дополнительные параметры <span class="text-red-400">*</span> — заполните хотя бы одно для сужения поиска
            </p>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-text-main mb-2">Никнеймы</label>
                <input type="text" id="comp-nicknames"
                  placeholder="octocat, johndoe (через запятую)"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all" />
              </div>
              <div>
                <label class="block text-sm font-medium text-text-main mb-2">Должность / роль</label>
                <input type="text" id="comp-position"
                  placeholder="CTO, ML Engineer"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all" />
              </div>
              <div>
                <label class="block text-sm font-medium text-text-main mb-2">Компания</label>
                <input type="text" id="comp-company"
                  placeholder="Яндекс, Google"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all" />
              </div>
              <div>
                <label class="block text-sm font-medium text-text-main mb-2">Город</label>
                <input type="text" id="comp-city"
                  placeholder="Москва"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all" />
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-text-main mb-2">Навыки для проверки</label>
                <input type="text" id="comp-skills"
                  placeholder="Python, Kubernetes, ML (через запятую)"
                  class="input-field w-full px-4 py-3 rounded-xl focus:outline-none transition-all" />
              </div>
            </div>
          </div>

          <!-- Кнопка -->
          <button type="submit"
            class="w-full px-6 py-3 bg-primary hover:bg-primary-hover text-white font-semibold rounded-xl transition-all shadow-soft">
            <i data-lucide="search" class="w-5 h-5 inline mr-2"></i>
            Найти
          </button>
        </form>
      </div>

      <!-- Результат -->
      <div id="competency-result"></div>

      <!-- История поисков -->
      ${renderCompetencyHistory()}
    </div>
  `;
}


// ============================================================
// RENDER: Список кандидатов (disambiguation)
// ============================================================

export function renderCandidates(candidates, query) {
  if (!candidates || candidates.length === 0) {
    return `
      <div class="bg-card rounded-2xl shadow-soft p-8 text-center slide-up">
        <i data-lucide="user-x" class="w-12 h-12 text-text-secondary mx-auto mb-4"></i>
        <h3 class="text-lg font-semibold text-text-main mb-2">Ничего не найдено</h3>
        <p class="text-text-secondary">Попробуйте изменить параметры поиска или добавить больше деталей.</p>
      </div>
    `;
  }

  return `
    <div class="bg-card rounded-2xl shadow-soft p-8 slide-up" style="animation-delay: 0.2s">
      <h2 class="text-xl font-semibold text-text-main mb-2">
        Найдено ${candidates.length} совпадений
      </h2>
      <p class="text-text-secondary text-sm mb-6">Уточните, кого вы ищете:</p>

      <div class="space-y-3">
        ${candidates.map((c, i) => `
          <div class="flex items-center gap-4 p-4 rounded-xl border border-card-border hover:border-primary/50 hover:bg-primary/[.05] transition-all cursor-pointer competency-candidate"
               data-candidate-index="${i}"
               data-full-name="${escapeHtml(c.full_name)}"
               data-company="${escapeHtml(c.current_company || '')}"
               data-position="${escapeHtml(c.current_position || '')}"
               data-city="${escapeHtml(c.city || '')}"
               data-accounts="${escapeHtml(JSON.stringify(c.selected_accounts || {}))}">
            <div class="w-12 h-12 rounded-full bg-primary/[.18] flex items-center justify-center shrink-0">
              ${c.photo_url
                ? `<img src="${c.photo_url}" class="w-12 h-12 rounded-full object-cover" alt="" />`
                : `<i data-lucide="user" class="w-5 h-5 text-primary"></i>`
              }
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-text-main truncate">${escapeHtml(c.full_name)}</div>
              <div class="text-sm text-text-secondary truncate">
                ${c.current_position ? escapeHtml(c.current_position) : 'Должность неизвестна'}
                ${c.current_company ? ` @ ${escapeHtml(c.current_company)}` : ''}
                ${c.city ? ` · ${escapeHtml(c.city)}` : ''}
              </div>
              ${c.skills_preview && c.skills_preview.length > 0
                ? `<div class="flex flex-wrap gap-1 mt-1">
                    ${c.skills_preview.slice(0, 4).map(s =>
                      `<span class="px-2 py-0.5 bg-surface rounded text-xs text-text-secondary">${escapeHtml(s)}</span>`
                    ).join('')}
                   </div>`
                : ''
              }
            </div>
            <div class="text-right shrink-0">
              <div class="text-lg font-bold ${c.match_score >= 70 ? 'text-green-400' : c.match_score >= 40 ? 'text-amber-400' : 'text-text-secondary'}">
                ${Math.round(c.match_score)}
              </div>
              <div class="text-xs text-text-secondary">score</div>
            </div>
            <div class="shrink-0">
              ${c.found_sources.map(s =>
                `<span class="inline-block px-2 py-0.5 bg-surface rounded text-xs text-text-secondary mr-1">${s}</span>`
              ).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}


// ============================================================
// RENDER: Полный отчёт
// ============================================================

export function renderProfileReport(profile) {
  const score = profile.competence_score || 0;
  const scoreColor = score >= 70 ? 'text-green-400' : score >= 40 ? 'text-amber-400' : 'text-red-400';
  const scoreBg = score >= 70 ? 'bg-green-900/30' : score >= 40 ? 'bg-amber-900/30' : 'bg-red-900/30';

  return `
    <div class="space-y-6 slide-up" style="animation-delay: 0.2s">

      <!-- Шапка профиля -->
      <div class="bg-card rounded-2xl shadow-soft p-8">
        <div class="flex items-start gap-6">
          <!-- Score -->
          <div class="w-24 h-24 rounded-2xl ${scoreBg} flex flex-col items-center justify-center shrink-0">
            <span class="text-3xl font-bold ${scoreColor}">${Math.round(score)}</span>
            <span class="text-xs text-text-secondary">/ 100</span>
          </div>
          <!-- Info -->
          <div class="flex-1">
            <h2 class="text-2xl font-bold text-text-main">${escapeHtml(profile.full_name || 'Неизвестно')}</h2>
            ${profile.current_position || profile.current_company
              ? `<p class="text-lg text-text-secondary mt-1">
                  ${profile.current_position ? escapeHtml(profile.current_position) : ''}
                  ${profile.current_company ? ` @ ${escapeHtml(profile.current_company)}` : ''}
                </p>`
              : ''
            }
            <div class="flex flex-wrap gap-2 mt-3">
              ${profile.sources.map(s =>
                `<span class="px-3 py-1 bg-primary/[.18] text-primary rounded-full text-xs font-medium">${s}</span>`
              ).join('')}
            </div>
          </div>
          <!-- PDF -->
          <button id="export-pdf-btn"
            class="px-4 py-2 bg-card border border-card-border rounded-xl text-sm font-medium text-text-main hover:bg-surface transition-all shrink-0">
            <i data-lucide="download" class="w-4 h-4 inline mr-1"></i>
            PDF
          </button>
        </div>

        ${profile.competence_assessment ? renderAssessmentSummary(profile.competence_assessment) : ''}
      </div>

      <!-- Red Flags -->
      ${profile.red_flags && profile.red_flags.length > 0 ? renderRedFlags(profile.red_flags) : ''}

      <!-- Карьера -->
      ${profile.experience && profile.experience.length > 0 ? renderExperience(profile.experience) : ''}

      <!-- Навыки -->
      ${profile.skills && profile.skills.length > 0 ? renderSkills(profile.skills) : ''}

      <!-- Публикации -->
      ${profile.articles && profile.articles.length > 0 ? renderArticles(profile.articles) : ''}

      <!-- Научные работы -->
      ${profile.publications && profile.publications.length > 0 ? renderPublications(profile.publications) : ''}

      <!-- GitHub -->
      ${profile.github ? renderGitHub(profile.github) : ''}

      <!-- Книги -->
      ${profile.books && profile.books.length > 0 ? renderBooks(profile.books) : ''}

      <!-- Соцсети -->
      ${profile.social_profiles && profile.social_profiles.length > 0 ? renderSocialProfiles(profile.social_profiles) : ''}

      <!-- OSINT проверки -->
      ${renderOSINTChecks(profile)}
    </div>
  `;
}


// ============================================================
// RENDER: Блоки отчёта
// ============================================================

function renderAssessmentSummary(assessment) {
  if (!assessment) return '';
  return `
    <div class="mt-6 pt-6 border-t border-card-border">
      <div class="grid grid-cols-4 gap-4">
        <div class="text-center">
          <div class="text-lg font-bold text-text-main">${assessment.experience_score || 0}</div>
          <div class="text-xs text-text-secondary">Опыт</div>
        </div>
        <div class="text-center">
          <div class="text-lg font-bold text-text-main">${assessment.technical_score || 0}</div>
          <div class="text-xs text-text-secondary">Технические</div>
        </div>
        <div class="text-center">
          <div class="text-lg font-bold text-text-main">${assessment.reputation_score || 0}</div>
          <div class="text-xs text-text-secondary">Репутация</div>
        </div>
        <div class="text-center">
          <div class="text-lg font-bold text-text-main">${assessment.overall_score || 0}</div>
          <div class="text-xs text-text-secondary">Общий</div>
        </div>
      </div>
      ${assessment.strengths && assessment.strengths.length > 0 ? `
        <div class="mt-4">
          <span class="text-xs font-medium text-green-400 mr-2">Сильные стороны:</span>
          ${assessment.strengths.map(s => `<span class="text-xs text-text-secondary mr-2">${escapeHtml(s)}</span>`).join('')}
        </div>
      ` : ''}
      ${assessment.concerns && assessment.concerns.length > 0 ? `
        <div class="mt-1">
          <span class="text-xs font-medium text-amber-400 mr-2">Риски:</span>
          ${assessment.concerns.map(c => `<span class="text-xs text-text-secondary mr-2">${escapeHtml(c)}</span>`).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

function renderRedFlags(flags) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="alert-triangle" class="w-5 h-5 inline mr-2 text-red-400"></i>
        Red Flags (${flags.length})
      </h3>
      <div class="space-y-3">
        ${flags.map(rf => {
          const color = rf.priority === 'CRITICAL' ? 'bg-red-900/30 border-red-500/30 text-red-400'
                      : rf.priority === 'HIGH' ? 'bg-orange-900/30 border-orange-500/30 text-orange-400'
                      : 'bg-amber-900/30 border-amber-500/30 text-amber-400';
          return `
            <div class="p-4 rounded-xl border ${color}">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-bold text-sm">${rf.priority}</span>
                <span class="text-xs opacity-70">${escapeHtml(rf.category)}</span>
              </div>
              <p class="text-sm">${escapeHtml(rf.description)}</p>
              ${rf.source ? `<p class="text-xs opacity-50 mt-1">Источник: ${escapeHtml(rf.source)}</p>` : ''}
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderExperience(experience) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="briefcase" class="w-5 h-5 inline mr-2 text-primary"></i>
        Карьера (${experience.length})
      </h3>
      <div class="space-y-4">
        ${experience.map(exp => `
          <div class="flex items-start gap-4 p-3 rounded-lg hover:bg-surface transition-colors">
            <div class="w-10 h-10 rounded-lg bg-primary/[.18] flex items-center justify-center shrink-0">
              <i data-lucide="building-2" class="w-4 h-4 text-primary"></i>
            </div>
            <div class="flex-1">
              <div class="font-medium text-text-main">${escapeHtml(exp.position)}</div>
              <div class="text-sm text-text-secondary">${escapeHtml(exp.company)}</div>
              ${exp.start_date || exp.end_date
                ? `<div class="text-xs text-text-secondary mt-1">${exp.start_date || '?'} — ${exp.end_date || 'н.в.'}</div>`
                : ''
              }
              ${exp.description ? `<div class="text-sm text-text-secondary mt-1">${escapeHtml(exp.description)}</div>` : ''}
            </div>
            <span class="text-xs text-text-secondary">${escapeHtml(exp.source || '')}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderSkills(skills) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="code-2" class="w-5 h-5 inline mr-2 text-primary"></i>
        Навыки (${skills.length})
      </h3>
      <div class="flex flex-wrap gap-2">
        ${skills.map(s => {
          const color = s.level === 'expert' ? 'bg-green-900/30 text-green-400 border-green-500/30'
                      : s.level === 'senior' ? 'bg-blue-900/30 text-blue-400 border-blue-500/30'
                      : 'bg-surface text-text-secondary border-card-border';
          return `
            <span class="px-3 py-1.5 rounded-lg border text-sm font-medium ${color}">
              ${escapeHtml(s.name)}
              ${s.level ? `<span class="text-xs opacity-60 ml-1">${s.level}</span>` : ''}
            </span>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function renderArticles(articles) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="file-text" class="w-5 h-5 inline mr-2 text-primary"></i>
        Статьи (${articles.length})
      </h3>
      <div class="space-y-3">
        ${articles.map(a => `
          <a href="${escapeHtml(a.url)}" target="_blank" rel="noopener"
             class="flex items-start gap-3 p-3 rounded-lg hover:bg-surface transition-colors group">
            <div class="w-8 h-8 rounded bg-surface flex items-center justify-center shrink-0 text-xs font-bold text-text-secondary">
              ${a.platform === 'habr' ? 'H' : a.platform === 'vc' ? 'VC' : a.platform === 'medium' ? 'M' : '?'}
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium text-text-main group-hover:text-primary transition-colors truncate">${escapeHtml(a.title)}</div>
              <div class="text-xs text-text-secondary mt-0.5">
                ${a.platform} ${a.date ? `· ${a.date.split('T')[0]}` : ''} ${a.views ? `· ${a.views.toLocaleString()} views` : ''}
              </div>
              ${a.tags && a.tags.length > 0
                ? `<div class="flex flex-wrap gap-1 mt-1">${a.tags.slice(0, 3).map(t =>
                    `<span class="px-1.5 py-0.5 bg-surface rounded text-xs text-text-secondary">${escapeHtml(t)}</span>`
                  ).join('')}</div>`
                : ''
              }
            </div>
          </a>
        `).join('')}
      </div>
    </div>
  `;
}

function renderPublications(publications) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="graduation-cap" class="w-5 h-5 inline mr-2 text-primary"></i>
        Научные работы (${publications.length})
      </h3>
      <div class="space-y-3">
        ${publications.map(p => `
          <div class="p-3 rounded-lg hover:bg-surface transition-colors">
            <div class="font-medium text-text-main">${escapeHtml(p.title)}</div>
            <div class="text-sm text-text-secondary mt-1">
              ${p.authors ? p.authors.join(', ') : ''} ${p.year ? `(${p.year})` : ''} ${p.venue ? `· ${p.venue}` : ''}
            </div>
            ${p.citations ? `<div class="text-xs text-primary mt-1">Цитирований: ${p.citations}</div>` : ''}
            ${p.url ? `<a href="${escapeHtml(p.url)}" target="_blank" class="text-xs text-primary hover:underline mt-1 inline-block">Подробнее →</a>` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderGitHub(gh) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="github" class="w-5 h-5 inline mr-2 text-primary"></i>
        GitHub — ${escapeHtml(gh.username)}
      </h3>
      <div class="grid grid-cols-4 gap-4 mb-4">
        <div class="text-center p-3 bg-surface rounded-xl">
          <div class="text-lg font-bold text-text-main">${gh.public_repos}</div>
          <div class="text-xs text-text-secondary">Repos</div>
        </div>
        <div class="text-center p-3 bg-surface rounded-xl">
          <div class="text-lg font-bold text-text-main">${gh.followers}</div>
          <div class="text-xs text-text-secondary">Followers</div>
        </div>
        <div class="text-center p-3 bg-surface rounded-xl">
          <div class="text-lg font-bold text-text-main">${gh.following}</div>
          <div class="text-xs text-text-secondary">Following</div>
        </div>
        <div class="text-center p-3 bg-surface rounded-xl">
          <div class="text-lg font-bold text-text-main">${gh.top_languages ? gh.top_languages.length : 0}</div>
          <div class="text-xs text-text-secondary">Languages</div>
        </div>
      </div>
      ${gh.top_languages && gh.top_languages.length > 0 ? `
        <div class="flex flex-wrap gap-2 mb-4">
          ${gh.top_languages.map(l =>
            `<span class="px-2 py-1 bg-primary/[.18] text-primary rounded text-xs font-medium">${escapeHtml(l)}</span>`
          ).join('')}
        </div>
      ` : ''}
      ${gh.notable_repos && gh.notable_repos.length > 0 ? `
        <div class="space-y-2">
          ${gh.notable_repos.slice(0, 5).map(r => `
            <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener"
               class="flex items-center justify-between p-2 rounded-lg hover:bg-surface transition-colors group">
              <div>
                <span class="font-medium text-text-main group-hover:text-primary transition-colors">${escapeHtml(r.name)}</span>
                ${r.description ? `<span class="text-xs text-text-secondary ml-2">${escapeHtml(r.description)}</span>` : ''}
              </div>
              <div class="flex items-center gap-2 text-xs text-text-secondary">
                ${r.language ? `<span>${escapeHtml(r.language)}</span>` : ''}
                <span>⭐ ${r.stars}</span>
              </div>
            </a>
          `).join('')}
        </div>
      ` : ''}
      <a href="${escapeHtml(gh.url)}" target="_blank" rel="noopener"
         class="inline-block mt-4 text-sm text-primary hover:underline">Открыть GitHub →</a>
    </div>
  `;
}

function renderBooks(books) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="book-open" class="w-5 h-5 inline mr-2 text-primary"></i>
        Книги (${books.length})
      </h3>
      <div class="space-y-3">
        ${books.map(b => `
          <div class="p-3 rounded-lg hover:bg-surface transition-colors">
            <div class="font-medium text-text-main">${escapeHtml(b.title)}</div>
            <div class="text-sm text-text-secondary mt-1">
              ${b.authors ? b.authors.join(', ') : ''} ${b.year ? `(${b.year})` : ''} ${b.publisher ? `· ${b.publisher}` : ''}
            </div>
            ${b.isbn ? `<div class="text-xs text-text-secondary mt-1">ISBN: ${b.isbn}</div>` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderSocialProfiles(profiles) {
  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="link" class="w-5 h-5 inline mr-2 text-primary"></i>
        Социальные профили (${profiles.length})
      </h3>
      <div class="flex flex-wrap gap-3">
        ${profiles.map(p => `
          <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener"
             class="flex items-center gap-2 px-4 py-2 bg-surface rounded-xl hover:bg-primary/[.18] transition-colors">
            <span class="text-sm font-medium text-text-main">${escapeHtml(p.platform)}</span>
            ${p.username ? `<span class="text-xs text-text-secondary">${escapeHtml(p.username)}</span>` : ''}
          </a>
        `).join('')}
      </div>
    </div>
  `;
}

function renderOSINTChecks(profile) {
  const checks = [];

  if (profile.is_sanctioned) {
    checks.push({ label: 'Санкции', value: 'НАЙДЕН В СПИСКАХ', color: 'text-red-400' });
  } else {
    checks.push({ label: 'Санкции', value: 'Чист', color: 'text-green-400' });
  }

  if (profile.is_pep) {
    checks.push({ label: 'PEP', value: 'Да', color: 'text-amber-400' });
  } else {
    checks.push({ label: 'PEP', value: 'Нет', color: 'text-green-400' });
  }

  if (profile.court_cases && profile.court_cases.length > 0) {
    checks.push({ label: 'Суды', value: `${profile.court_cases.length} дел`, color: 'text-amber-400' });
  } else {
    checks.push({ label: 'Суды', value: 'Нет', color: 'text-green-400' });
  }

  if (profile.enforcement_proceedings && profile.enforcement_proceedings.length > 0) {
    checks.push({ label: 'ФССП', value: `${profile.enforcement_proceedings.length} производств`, color: 'text-amber-400' });
  } else {
    checks.push({ label: 'ФССП', value: 'Нет', color: 'text-green-400' });
  }

  if (profile.news_mentions && profile.news_mentions.some(n => n.is_negative)) {
    checks.push({ label: 'СМИ', value: 'Есть негатив', color: 'text-red-400' });
  } else {
    checks.push({ label: 'СМИ', value: 'Чист', color: 'text-green-400' });
  }

  return `
    <div class="bg-card rounded-2xl shadow-soft p-6">
      <h3 class="text-lg font-semibold text-text-main mb-4">
        <i data-lucide="shield-check" class="w-5 h-5 inline mr-2 text-primary"></i>
        OSINT проверки
      </h3>
      <div class="grid grid-cols-5 gap-3">
        ${checks.map(c => `
          <div class="text-center p-3 bg-surface rounded-xl">
            <div class="text-sm font-bold ${c.color}">${c.value}</div>
            <div class="text-xs text-text-secondary mt-1">${c.label}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}


// ============================================================
// RENDER: История поисков
// ============================================================

function renderCompetencyHistory() {
  const history = state.competencyHistory || [];
  if (history.length === 0) return '';

  return `
    <div class="bg-card rounded-2xl shadow-soft overflow-hidden slide-up" style="animation-delay: 0.3s">
      <div class="p-6 border-b border-card-border">
        <h2 class="text-xl font-semibold text-text-main">История поисков</h2>
      </div>
      <div class="divide-y divide-card-border">
        ${history.map(record => `
          <div class="p-4 hover:bg-surface transition-colors">
            <div class="flex items-center justify-between">
              <div>
                <span class="font-medium text-text-main">${escapeHtml(record.full_name)}</span>
                ${record.company ? `<span class="text-sm text-text-secondary ml-2">@ ${escapeHtml(record.company)}</span>` : ''}
              </div>
              <div class="flex items-center gap-3">
                ${record.score !== null
                  ? `<span class="text-sm font-bold ${record.score >= 70 ? 'text-green-400' : record.score >= 40 ? 'text-amber-400' : 'text-red-400'}">${Math.round(record.score)}</span>`
                  : ''
                }
                <span class="text-xs text-text-secondary">${record.date}</span>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}


// ============================================================
// UTILS
// ============================================================

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
