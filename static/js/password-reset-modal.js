// static/js/password-reset-modal.js
(function () {
  const modal = document.getElementById('password-reset-modal');
  const form = document.getElementById('password-reset-form');
  const messagesDiv = document.getElementById('password-reset-messages');

  if (!modal || !form) return;

  // Функция открытия
  function openPasswordResetModal() {
    window.modalManager.open('password-reset-modal');
  }

  // Функция показа сообщений
  function showMessage(message, type = 'error') {
    if (!messagesDiv) return;

    messagesDiv.classList.remove('hidden');
    messagesDiv.className = `mb-4 p-3 rounded-lg text-sm ${
      type === 'error' 
        ? 'bg-red-900/50 border border-red-700 text-red-200' 
        : 'bg-green-900/50 border border-green-700 text-green-200'
    }`;
    messagesDiv.textContent = message;
  }

  // Перехват кликов по ссылкам восстановления пароля
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;

    try {
      const url = new URL(link.href, window.location.origin);
      if (url.pathname.startsWith('/accounts/password/reset')) {
        e.preventDefault();
        openPasswordResetModal();
      }
    } catch (err) {
      // Игнорируем ошибки парсинга URL
    }
  });

  // Переключение между модалками
  document.addEventListener('click', (e) => {
    const switchBtn = e.target.closest('[data-switch-to]');
    if (!switchBtn || !switchBtn.closest('#password-reset-modal')) return;

    e.preventDefault();
    const targetModal = switchBtn.dataset.switchTo;

    window.modalManager.close('password-reset-modal');

    setTimeout(() => {
      window.modalManager.open(targetModal);
    }, 150);
  });

  // Сброс формы при закрытии
  if (modal) {
    modal.addEventListener('modal:closed', () => {
      if (form) form.reset();
      if (messagesDiv) messagesDiv.classList.add('hidden');
    });
  }

  // Глобальная функция
  window.openPasswordResetModal = openPasswordResetModal;
})();