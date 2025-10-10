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
      e.preventDefault(); // Предотвращаем стандартную отправку
      
      if (messagesDiv) messagesDiv.classList.add('hidden');

      // Валидация
      if (!validatePasswords()) {
        return false;
      }

      // Проверка согласия с правилами
      const termsCheckbox = form.querySelector('input[name="terms"]');
      if (termsCheckbox && !termsCheckbox.checked) {
        showSignupMessage('Необходимо согласиться с правилами сервиса', 'error');
        return false;
      }

      // Блокировка кнопки
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></span>Регистрация...';
      }

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
          // Есть редирект - проверяем URL
          if (data.location.includes('/accounts/confirm-email/')) {
            // Показываем сообщение об успешной регистрации
            showSignupMessage('Регистрация успешна! Проверьте email для подтверждения аккаунта.', 'success');
            
            // Закрываем модальное окно через 3 секунды
            setTimeout(() => {
              window.modalManager.close('signup-modal');
              // Показываем модальное окно с информацией о подтверждении email
              if (window.modalManager.open) {
                // Получаем email из формы
                const emailInput = form.querySelector('input[name="email"]');
                if (emailInput) {
                  const emailElement = document.getElementById('verification-email');
                  if (emailElement) {
                    emailElement.textContent = emailInput.value;
                  }
                }
                window.modalManager.open('email-verification-modal');
              }
            }, 3000);
          } else {
            // Другой редирект - переходим на страницу
            window.location.href = data.location;
          }
        } else if (data.form && data.form.errors && data.form.errors.length > 0) {
          // Есть ошибки формы
          let errorMessage = '';
          data.form.errors.forEach(error => {
            errorMessage += error + ' ';
          });
          showSignupMessage(errorMessage.trim(), 'error');
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
            showSignupMessage(errorMessage.trim(), 'error');
          } else {
            showSignupMessage('Произошла ошибка при регистрации', 'error');
          }
        } else {
          // Неожиданный ответ
          showSignupMessage('Произошла ошибка при регистрации', 'error');
        }
      })
      .catch(error => {
        console.error('Error:', error);
        showSignupMessage('Произошла ошибка при регистрации', 'error');
      })
      .finally(() => {
        // Разблокируем кнопку
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Зарегистрироваться';
        }
      });

      return false;
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