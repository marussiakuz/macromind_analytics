import './style.css';
import { dismissNotification } from './notifications.js';
import { state } from './state.js';
import { renderApp } from './render/app.js';

document.body.addEventListener('click', (e) => {
  const dismissBtn = e.target.closest('[data-dismiss-notification]');
  if (dismissBtn) {
    e.preventDefault();
    dismissNotification(dismissBtn.getAttribute('data-dismiss-notification'));
  }
});

const sp = new URLSearchParams(window.location.search);
if (sp.get('startup') === '1') {
  state.currentRole = 'startup';
  // Переход со страницы экспертизы («К приложению» / логотип): сразу дашборд стартапа с приветствием основателя
  state.currentPage = 'startup';
  window.history.replaceState({}, '', window.location.pathname);
}

renderApp();
