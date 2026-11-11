import { state } from './state.js';
import { deleteAnalysis, fetchModelStatus, getAnalysis, listAnalyses, uploadDeck } from './api/pitchDeck.js';

const POLL_MS = 3000;
let pollTimer = null;

function hasRunning(items) {
  return items.some(item => item.status === 'queued' || item.status === 'running');
}

async function refreshList(renderApp) {
  try {
    state.pitchDeckList = await listAnalyses();
    const active = state.pitchDeckActive;
    if (active && !active.result) {
      const current = state.pitchDeckList.find(item => item.id === active.id);
      if (current?.status === 'done') state.pitchDeckActive = await getAnalysis(active.id);
    }
    state.pitchDeckError = null;
  } catch {
    state.pitchDeckError = 'Сервис анализа недоступен. Проверьте, что API запущен.';
  }
  schedulePoll(renderApp);
  renderApp();
}

function schedulePoll(renderApp) {
  clearTimeout(pollTimer);
  pollTimer = null;
  if (hasRunning(state.pitchDeckList) && state.currentFundTab === 'pitch-decks') {
    pollTimer = setTimeout(() => refreshList(renderApp), POLL_MS);
  }
}

/** Load model status and the deck list once when the tab opens. */
export async function loadPitchDeckTab(renderApp) {
  try {
    state.pitchDeckModel = await fetchModelStatus();
  } catch {
    state.pitchDeckModel = { available: false, message: 'Сервис анализа недоступен' };
  }
  await refreshList(renderApp);
}

export function setupPitchDeckListeners(renderApp) {
  document.getElementById('pitchdeck-upload')?.addEventListener('click', async () => {
    const file = document.getElementById('pitchdeck-file')?.files?.[0];
    if (!file) {
      state.pitchDeckError = 'Выберите файл PDF или PPTX';
      renderApp();
      return;
    }
    state.pitchDeckUploading = true;
    state.pitchDeckError = null;
    renderApp();
    try {
      const created = await uploadDeck(file);
      state.pitchDeckActive = { id: created.id, result: null };
      state.pitchDeckSlide = null;
    } catch (error) {
      state.pitchDeckError = error.message;
    }
    state.pitchDeckUploading = false;
    await refreshList(renderApp);
  });

  document.querySelectorAll('.pd-open').forEach(button => {
    button.addEventListener('click', async () => {
      try {
        state.pitchDeckActive = await getAnalysis(button.dataset.id);
        state.pitchDeckSlide = null;
      } catch (error) {
        state.pitchDeckError = error.message;
      }
      renderApp();
    });
  });

  document.querySelectorAll('.pd-delete').forEach(button => {
    button.addEventListener('click', async () => {
      try {
        await deleteAnalysis(button.dataset.id);
        if (state.pitchDeckActive?.id === button.dataset.id) state.pitchDeckActive = null;
      } catch (error) {
        state.pitchDeckError = error.message;
      }
      await refreshList(renderApp);
    });
  });

  document.querySelectorAll('.pd-slide-link').forEach(button => {
    button.addEventListener('click', () => {
      state.pitchDeckSlide = Number(button.dataset.slide);
      renderApp();
    });
  });
}
