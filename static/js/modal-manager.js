// static/js/modal-manager.js
/**
 * Универсальный менеджер модальных окон
 */

class ModalManager {
  constructor() {
    this.activeModal = null;
    this.init();
  }

  /**
   * Инициализация всех модальных окон на странице
   */
  init() {
    // Предотвращаем повторную инициализацию
    if (window.__modalManagerInitialized__) return;
    window.__modalManagerInitialized__ = true;

    this.bindEvents();
    this.handleEscapeKey();
  }

  /**
   * Привязка событий к элементам
   */
  bindEvents() {
    // Делегирование событий на document для динамически создаваемых элементов
    document.addEventListener('click', (e) => {
      const target = e.target.closest('[data-modal-open]');
      if (target) {
        e.preventDefault();
        const modalId = target.dataset.modalOpen;
        this.open(modalId);
      }
    });

    document.addEventListener('click', (e) => {
      const target = e.target.closest('[data-modal-close]');
      if (target) {
        e.preventDefault();
        const modalId = target.dataset.modalClose;
        this.close(modalId);
      }
    });

    document.addEventListener('click', (e) => {
      const target = e.target.closest('[data-modal-overlay]');
      if (target && e.target === target) {
        const modalId = target.dataset.modalOverlay;
        this.close(modalId);
      }
    });
  }

  /**
   * Обработка клавиши Escape
   */
  handleEscapeKey() {
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.activeModal) {
        this.close(this.activeModal);
      }
    });
  }

  /**
   * Открыть модальное окно
   * @param {string} modalId - ID модального окна
   */
  open(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
      console.warn(`Modal with id "${modalId}" not found`);
      return;
    }

    // Закрываем предыдущее модальное окно, если оно открыто
    if (this.activeModal && this.activeModal !== modalId) {
      this.close(this.activeModal);
    }

    modal.classList.add('modal-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-is-open');

    this.activeModal = modalId;

    // Вызываем кастомное событие для возможности подписки
    this.dispatchEvent(modal, 'modal:opened', { modalId });
  }

  /**
   * Закрыть модальное окно
   * @param {string} modalId - ID модального окна
   */
  close(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) {
      console.warn(`Modal with id "${modalId}" not found`);
      return;
    }

    modal.classList.remove('modal-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-is-open');

    if (this.activeModal === modalId) {
      this.activeModal = null;
    }

    // Вызываем кастомное событие
    this.dispatchEvent(modal, 'modal:closed', { modalId });
  }

  /**
   * Переключить состояние модального окна
   * @param {string} modalId - ID модального окна
   */
  toggle(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    if (modal.classList.contains('modal-open')) {
      this.close(modalId);
    } else {
      this.open(modalId);
    }
  }

  /**
   * Проверить, открыто ли модальное окно
   * @param {string} modalId - ID модального окна
   * @returns {boolean}
   */
  isOpen(modalId) {
    const modal = document.getElementById(modalId);
    return modal ? modal.classList.contains('modal-open') : false;
  }

  /**
   * Отправить кастомное событие
   * @param {HTMLElement} element - Элемент
   * @param {string} eventName - Название события
   * @param {Object} detail - Данные события
   */
  dispatchEvent(element, eventName, detail = {}) {
    const event = new CustomEvent(eventName, {
      bubbles: true,
      cancelable: true,
      detail
    });
    element.dispatchEvent(event);
  }
}

// Инициализация при загрузке DOM
document.addEventListener('DOMContentLoaded', () => {
  window.modalManager = new ModalManager();
});

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ModalManager;
}