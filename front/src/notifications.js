import { createIcons, icons } from 'lucide';
import { state } from './state.js';
import { generateId } from './utils/helpers.js';

export function showNotification(message, type = 'info') {
  const id = generateId();
  state.notifications.push({ id, message, type });
  renderNotifications();
  setTimeout(() => {
    state.notifications = state.notifications.filter((n) => n.id !== id);
    renderNotifications();
  }, 4000);
}

export function dismissNotification(id) {
  state.notifications = state.notifications.filter((n) => n.id !== id);
  renderNotifications();
}

export function renderNotifications() {
  const container = document.getElementById('notifications-container');
  if (!container) return;
  container.innerHTML = state.notifications
    .map(
      (n) => `
    <div class="notification-enter flex items-center gap-3 px-4 py-3 bg-card rounded-xl shadow-medium border border-card-border min-w-[300px]">
      <i data-lucide="${n.type === 'success' ? 'check' : n.type === 'error' ? 'alert-circle' : 'info'}" class="w-5 h-5 ${n.type === 'success' ? 'text-green-500' : n.type === 'error' ? 'text-red-400' : 'text-blue-500'}"></i>
      <span class="text-sm text-text-main">${n.message}</span>
      <button type="button" class="ml-auto p-1 hover:bg-[#222222] rounded transition-colors" data-dismiss-notification="${n.id}">
        <i data-lucide="x" class="w-4 h-4 text-text-secondary"></i>
      </button>
    </div>
  `
    )
    .join('');
  createIcons({ icons });
}

export function renderNotificationsHTML() {
  return `
    <div id="notifications-container" class="fixed top-20 right-4 z-50 space-y-2">
      ${state.notifications
        .map(
          (n) => `
        <div class="notification-enter flex items-center gap-3 px-4 py-3 bg-card rounded-xl shadow-medium border border-card-border min-w-[300px]">
          <i data-lucide="${n.type === 'success' ? 'check' : n.type === 'error' ? 'alert-circle' : 'info'}" class="w-5 h-5 ${n.type === 'success' ? 'text-green-500' : n.type === 'error' ? 'text-red-400' : 'text-blue-500'}"></i>
          <span class="text-sm text-text-main">${n.message}</span>
          <button class="ml-auto p-1 hover:bg-[#222222] rounded transition-colors" data-dismiss-notification="${n.id}">
            <i data-lucide="x" class="w-4 h-4 text-text-secondary"></i>
          </button>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}
