// static/js/signup-modal.js
(function () {
  const modal = document.getElementById('signup-modal');
  const form = document.getElementById('signup-form');
  const messagesDiv = document.getElementById('signup-messages');
  const nextField = document.getElementById('signup-next-field');
  const submitBtn = document.getElementById('signup-submit-btn');

  if (!modal || !form) return;

  // Функция открытия
  function openSignupModal(nextUrl) {
    if (nextUrl && nextField) {
      nextField.value = nextUrl;
    }
    window.modalManager.open('signup-modal');

    setTimeout(() => {
      const firstInput = form.querySelector('input[type="email"]');
      if (firstInput) firstInput.focus();
    }, 100);
  }

  // Функция показа сообщений
  function showSignupMessage(message, type = 'error') {
    if (!messagesDiv) return;

    messagesDiv.classList.remove('hidden');
    messagesDiv.className = `mb-4 p-3 rounded-lg text-sm ${
      type === 'error' 
        ? 'bg-red-900/50 border border-red-700 text-red-200' 
        : type === 'success'
        ? 'bg-green-900/50 border border-green-700 text-green-200'
        : 'bg-blue-900/50 border border-blue-700 text-blue-200'
    }`;

    messagesDiv.textContent = message;
  }

  // Валидация паролей
  function validatePasswords() {
    const password1 = form.querySelector('input[name="password1"]');
    const password2 = form.querySelector('input[name="password2"]');

    if (!password1 || !password2) return true;

    if (password1.value !== password2.value) {
      showSignupMessage('Пароли не совпадают', 'error');
      password2.focus();
      return false;
    }

    if (password1.value.length < 8) {
      showSignupMessage('Пароль должен содержать минимум 8 символов', 'error');
      password1.focus();
      return false;
    }

    return true;
  }

  // Обработка отправки формы
  if (form) {
    form.addEventListener('submit', function(e) {
      // НЕ предотвращаем отправку, проверяем валидацию
      if (messagesDiv) messagesDiv.classList.add('hidden');

      // Валидация
      if (!validatePasswords()) {
        e.preventDefault();
        return false;
      }

      // Проверка согласия с правилами
      const termsCheckbox = form.querySelector('input[name="terms"]');
      if (termsCheckbox && !termsCheckbox.checked) {
        e.preventDefault();
        showSignupMessage('Необходимо согласиться с правилами сервиса', 'error');
        return false;
      }

      // Блокировка кнопки
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></span>Регистрация...';
      }

      // Форма отправляется стандартно - Django обработает и перенаправит
      return true;
    });
  }

  // Переключение между модалками
  document.addEventListener('click', (e) => {
    const switchBtn = e.target.closest('[data-switch-to]');
    if (!switchBtn || !switchBtn.closest('#signup-modal')) return;

    e.preventDefault();
    const targetModal = switchBtn.dataset.switchTo;

    window.modalManager.close('signup-modal');
    setTimeout(() => {
      window.modalManager.open(targetModal);
    }, 150);
  });

  // Перехват кликов по ссылкам регистрации
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;

    try {
      const url = new URL(link.href, window.location.origin);
      if (url.pathname.startsWith('/accounts/signup')) {
        e.preventDefault();
        const nextUrl = url.searchParams.get('next') || window.location.pathname + window.location.search;
        openSignupModal(nextUrl);
      }
    } catch (err) {}
  });

  // Автооткрытие на странице signup
  if (window.location.pathname.startsWith('/accounts/signup')) {
    const nextUrl = new URLSearchParams(window.location.search).get('next');
    openSignupModal(nextUrl);
  }

  // Сброс формы при закрытии
  if (modal) {
    modal.addEventListener('modal:closed', () => {
      if (form) form.reset();
      if (messagesDiv) messagesDiv.classList.add('hidden');
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Зарегистрироваться';
      }
    });
  }

  window.openSignupModal = openSignupModal;
})();