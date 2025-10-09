(function () {
  const modal = document.getElementById('authModal');
  const backdrop = document.getElementById('authBackdrop');
  const closeBtn = document.getElementById('authClose');

  function open(next) {
    if (next) {
      // Прокидываем next в hidden поле формы
      const form = modal.querySelector('form');
      let hidden = form.querySelector('input[name="next"]');
      if (!hidden) {
        hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'next';
        form.appendChild(hidden);
      }
      hidden.value = next;
    }
    modal.classList.remove('hidden');
    backdrop.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');

    // автофокус
    const first = modal.querySelector('input, select, textarea, button');
    if (first) first.focus();
  }

  function close() {
    modal.classList.add('hidden');
    backdrop.classList.add('hidden');
    document.body.classList.remove('overflow-hidden');
  }

  // Закрытие
  closeBtn && closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  // Перехватываем клики по ссылкам /accounts/login/ чтобы открыть модалку
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]');
    if (!a) return;
    const url = new URL(a.href, window.location.origin);
    if (url.pathname.startsWith('/accounts/login')) {
      e.preventDefault();
      open(url.searchParams.get('next') || window.location.pathname + window.location.search);
    }
  });

  // Если уже на /accounts/login/ — открыть автоматически (с SEO-совместимостью)
  if (window.location.pathname.startsWith('/accounts/login')) {
    open(new URLSearchParams(window.location.search).get('next'));
    // Не меняем URL: страница доступна и как отдельный роут
  }
})();
