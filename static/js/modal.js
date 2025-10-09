(function () {
  const modal = document.getElementById('authModal');
  const backdrop = document.getElementById('authModalBackdrop');
  const closeBtn = document.getElementById('authModalClose');

  if (!modal || !backdrop) return;

  function close() {
    modal.classList.remove('is-open');
    backdrop.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    backdrop.setAttribute('aria-hidden', 'true');
    // Если страница — чисто страница логина, можно вернуть на previous page:
    // history.length > 1 && history.back();
  }

  // Уже открыто по умолчанию (класс is-open в шаблоне).
  // Навешиваем обработчики:
  closeBtn && closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', (e) => {
    // клик по подложке закрывает
    if (e.target === backdrop) close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
})();
