import { createIcons, icons } from 'lucide';
import { state } from '../state.js';
import { renderLoginPage } from './login.js';
import { renderStartupDashboard } from './startup.js';
import { renderFundDashboard } from './fund.js';
import { renderProjectCard } from './project.js';
import { setupEventListeners } from '../events.js';

export function renderApp() {
  const app = document.getElementById('app');
  if (!app) return;

  switch (state.currentPage) {
    case 'login':
      app.innerHTML = renderLoginPage();
      break;
    case 'startup':
      app.innerHTML = renderStartupDashboard();
      break;
    case 'fund':
      app.innerHTML = renderFundDashboard();
      break;
    case 'project':
      app.innerHTML = renderProjectCard();
      break;
    default:
      app.innerHTML = renderLoginPage();
  }

  createIcons({ icons });
  setupEventListeners(renderApp);
}
