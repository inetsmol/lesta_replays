// static/js/auth-modal.js
(function () {
  const modal = document.getElementById('auth-modal');
  const form = document.getElementById('auth-form');
  const messagesDiv = document.getElementById('auth-messages');
  const nextField = document.getElementById('auth-next-field');

  if (!modal) return;

  // Функция открытия с передачей next параметра
  function openAuthModal(nextUrl) {
    if (nextUrl && nextField) {
      nextField.value = nextUrl;
    }
    window.modalManager.open('auth-modal');
    
    // Автофокус на первом поле
    setTimeout(() => {
      const firstInput = form.querySelector('input[type="text"], input[type="email"]');
      if (firstInput) firstInput.focus();
    }, 100);
  }

  // Функция показа сообщений об ошибках
  function showAuthMessage(message, type = 'error') {
    if (!messagesDiv) return;
    
    messagesDiv.classList.remove('hidden');
    messagesDiv.className = `mb-4 p-3 rounded-lg text-sm ${
      type === 'error' 
        ? 'bg-red-900/50 border border-red-700 text-red-200' 
        : 'bg-blue-900/50 border border-blue-700 text-blue-200'
    }`;
    messagesDiv.textContent = message;
  }

  // Перехват кликов по ссылкам на страницу логина
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;
    
    try {
      const url = new URL(link.href, window.location.origin);
      if (url.pathname.startsWith('/accounts/login')) {
        e.preventDefault();
        const nextUrl = url.searchParams.get('next') || window.location.pathname + window.location.search;
        openAuthModal(nextUrl);
      }
    } catch (err) {
      // Игнорируем ошибки парсинга URL
    }
  });

  // Если находимся на странице /accounts/login/ - открыть модалку автоматически
  if (window.location.pathname.startsWith('/accounts/login')) {
    const nextUrl = new URLSearchParams(window.location.search).get('next');
    openAuthModal(nextUrl);
  }

  // Обработка отправки формы авторизации
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault(); // Предотвращаем стандартную отправку
      
      if (messagesDiv) messagesDiv.classList.add('hidden');

      // Отправляем форму через AJAX
      const formData = new FormData(form);
      
      fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.location) {
          // Есть редирект - значит авторизация успешна
          window.location.href = data.location;
        } else if (data.form && data.form.errors && data.form.errors.length > 0) {
          // Есть ошибки формы
          let errorMessage = '';
          data.form.errors.forEach(error => {
            errorMessage += error + ' ';
          });
          showAuthMessage(errorMessage.trim(), 'error');
        } else if (data.html) {
          // Есть HTML с ошибками
          const parser = new DOMParser();
          const doc = parser.parseFromString(data.html, 'text/html');
          const errorElements = doc.querySelectorAll('.errorlist, .alert-danger');
          
          if (errorElements.length > 0) {
            let errorMessage = '';
            errorElements.forEach(el => {
              errorMessage += el.textContent + ' ';
            });
            showAuthMessage(errorMessage.trim(), 'error');
          } else {
            showAuthMessage('Неверный логин или пароль', 'error');
          }
        } else {
          // Неожиданный ответ
          showAuthMessage('Произошла ошибка при авторизации', 'error');
        }
      })
      .catch(error => {
        console.error('Error:', error);
        showAuthMessage('Произошла ошибка при авторизации', 'error');
      });

      return false;
    });
  }

  // Сброс формы при закрытии
  if (modal) {
    modal.addEventListener('modal:closed', () => {
      if (form) form.reset();
      if (messagesDiv) messagesDiv.classList.add('hidden');
    });
  }

  // Глобальная функция для открытия из других скриптов
  window.openAuthModal = openAuthModal;
    // Переключение на модалку регистрации
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href*="account_signup"]');
    if (!link || !link.closest('#auth-modal')) return;

    e.preventDefault();
    window.modalManager.close('auth-modal');

    setTimeout(() => {
      if (window.openSignupModal) {
        const nextUrl = nextField?.value || window.location.pathname;
        window.openSignupModal(nextUrl);
      }
    }, 150);
  });

    // Переключение на модалку восстановления пароля
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href*="account_reset_password"]');
    if (!link || !link.closest('#auth-modal')) return;

    e.preventDefault();
    window.modalManager.close('auth-modal');

    setTimeout(() => {
      if (window.modalManager) {
        window.modalManager.open('password-reset-modal');
      }
    }, 150);
  });
})();