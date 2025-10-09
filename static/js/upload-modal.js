// static/js/upload-modal.js
document.addEventListener('DOMContentLoaded', function () {
  if (window.__uploadModalInitialized__) return;
  window.__uploadModalInitialized__ = true;

  const MAX_FILES = 5;

  const uploadBtn = document.getElementById('upload-replay-btn');
  const modal = document.getElementById('upload-modal');
  const uploadForm = document.getElementById('upload-form');
  const uploadArea = document.getElementById('upload-area');
  const fileInput = document.getElementById('file-input');
  const selectedBox = document.getElementById('selected-file');
  const fileInfo = document.getElementById('file-info');
  const submitBtn = document.getElementById('submit-upload');
  const uploadStatus = document.querySelector('.upload-status');

  const alertModal = document.getElementById('alert-modal');
  const alertMsgEl = document.getElementById('alert-message');
  const alertTitle = document.getElementById('alert-title');

  if (!modal || !uploadForm) return;

  let selectedFiles = [];
  let isFileDialogOpen = false;

  // Открытие модального окна
  if (uploadBtn) {
    uploadBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.modalManager.open('upload-modal');
    });
  }

  // Сброс формы при закрытии модального окна
  modal.addEventListener('modal:closed', () => {
    resetForm();
  });

  // Функция сброса формы
  function resetForm() {
    selectedFiles = [];
    if (fileInput) fileInput.value = '';
    if (fileInfo) fileInfo.innerHTML = '';
    if (selectedBox) selectedBox.classList.add('hidden');
    if (submitBtn) submitBtn.disabled = true;
    setStatus('Загрузить файлы', false);
  }

  // Drag & Drop
  if (uploadArea) {
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    });

    uploadArea.addEventListener('click', (e) => {
      if (e.target !== fileInput) {
        openFilePickerOnce();
      }
    });

    uploadArea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openFilePickerOnce();
      }
    });
  }

  // Обработка выбора файлов
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        addFiles(e.target.files);
      }
    });
  }

  // Открытие диалога выбора файлов
  function openFilePickerOnce() {
    if (!fileInput || isFileDialogOpen) return;

    isFileDialogOpen = true;
    fileInput.value = '';
    fileInput.click();

    const release = () => {
      isFileDialogOpen = false;
      window.removeEventListener('focus', release, true);
      fileInput.removeEventListener('change', release);
    };
    window.addEventListener('focus', release, true);
    fileInput.addEventListener('change', release, { once: true });
  }

  // Добавление файлов
  function addFiles(list) {
    if (selectedFiles.length >= MAX_FILES) {
      showMessage(`Лимит ${MAX_FILES} файлов за один раз. Удалите лишний файл, чтобы добавить новый.`, 'error');
      return;
    }
    const remaining = MAX_FILES - selectedFiles.length;
    const filesArr = Array.from(list);
    let added = 0;

    for (const f of filesArr) {
      if (added >= remaining) break;
      if (!validateFile(f)) continue;
      if (!selectedFiles.find(x => x.file.name === f.name && x.file.size === f.size)) {
        selectedFiles.push({ file: f, desc: '' });
        added += 1;
      }
    }

    if (filesArr.length > added) {
      showMessage(`Можно добавить не более ${MAX_FILES} файлов. Добавлены только первые ${added} из ${filesArr.length}.`, 'error');
    }

    renderSelected();
  }

  // Валидация файла
  function validateFile(file) {
    if (!file.name.toLowerCase().endsWith('.mtreplay')) {
      showMessage(`«${file.name}» — не .mtreplay`, 'error');
      return false;
    }
    if (file.size > 50 * 1024 * 1024) {
      showMessage(`«${file.name}» — больше 50MB`, 'error');
      return false;
    }
    return true;
  }

  // Форматирование размера файла
  function fmtBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  }

  // Экранирование HTML
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  // Отрисовка списка выбранных файлов
  function renderSelected() {
    if (!fileInfo || !selectedBox) return;
    if (selectedFiles.length === 0) {
      selectedBox.classList.add('hidden');
      if (submitBtn) submitBtn.disabled = true;
      return;
    }
    selectedBox.classList.remove('hidden');
    if (submitBtn) submitBtn.disabled = false;

    const total = selectedFiles.reduce((s, item) => s + item.file.size, 0);
    const left = Math.max(0, MAX_FILES - selectedFiles.length);

    fileInfo.innerHTML = `
      <div class="text-gray-400 text-sm mb-3 pb-3 border-b border-dashed border-gray-700">
        Выбрано: ${selectedFiles.length}/${MAX_FILES}${left ? ` (можно добавить ещё ${left})` : ''} • ${fmtBytes(total)}
      </div>
      <div class="space-y-2">
        ${selectedFiles.map((item, i) => `
          <div class="bg-gray-900 border border-gray-700 rounded-lg p-3 transition-all hover:border-gray-600">
            <div class="flex items-center gap-2 mb-2">
              <span class="flex-1 text-gray-200 text-sm truncate" title="${escapeHtml(item.file.name)}">
                ${escapeHtml(item.file.name)}
              </span>
              <span class="text-gray-400 text-xs whitespace-nowrap">
                ${fmtBytes(item.file.size)}
              </span>
              <button type="button" 
                      class="w-7 h-7 flex items-center justify-center rounded-md bg-red-700/20 text-red-600 hover:bg-red-700 hover:text-white transition-all flex-shrink-0"
                      data-remove="${i}"
                      aria-label="Удалить">
                ✕
              </button>
            </div>
            <input type="text"
                   class="w-full px-3 py-2 rounded-lg border border-gray-700 bg-gray-900 text-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-transparent"
                   data-desc-idx="${i}"
                   maxlength="60"
                   placeholder="Короткое описание (60 символов)"
                   value="${escapeHtml(item.desc || '')}">
          </div>
        `).join('')}
      </div>

      <div id="upload-progress" class="hidden relative mt-4 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div class="bar absolute inset-0 bg-gradient-to-r from-green-600 to-green-500 transition-all duration-200"></div>
        <span class="label absolute -top-6 right-0 text-xs text-gray-400">0%</span>
      </div>
    `;

    // Привязка событий к кнопкам удаления
    fileInfo.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const idx = parseInt(e.currentTarget.dataset.remove, 10);
        removeAt(idx);
      });
    });

    // Привязка событий к полям описания
    fileInfo.querySelectorAll('[data-desc-idx]').forEach(input => {
      input.addEventListener('input', (e) => {
        const idx = parseInt(e.currentTarget.dataset.descIdx, 10);
        if (idx >= 0 && idx < selectedFiles.length) {
          selectedFiles[idx].desc = e.currentTarget.value.slice(0, 60);
        }
      });
    });
  }

  // Удаление файла
  function removeAt(idx) {
    selectedFiles.splice(idx, 1);
    renderSelected();
  }

  // Установка статуса кнопки
  function setStatus(text, loading = false) {
    if (!uploadStatus) return;
    uploadStatus.innerHTML = loading ?
      `<span class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>${text}` : text;
  }

  // Установка прогресса
  function setProgress(pct) {
    const box = document.getElementById('upload-progress');
    if (!box) return;
    const bar = box.querySelector('.bar');
    const lbl = box.querySelector('.label');
    box.classList.remove('hidden');
    bar.style.width = `${pct}%`;
    lbl.textContent = `${pct}%`;
  }

  // Показать сообщение
  function showMessage(text, type = 'info') {
    const container = ensureMessagesContainer();
    const el = document.createElement('div');
    el.className = `message message--${type} px-4 py-3 rounded-lg mb-2 ${type === 'error' ? 'bg-red-900/50 border border-red-700 text-red-200' : 'bg-blue-900/50 border border-blue-700 text-blue-200'}`;
    el.textContent = text;
    container.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  function ensureMessagesContainer() {
    let container = document.querySelector('.messages');
    if (!container) {
      container = document.createElement('div');
      container.className = 'messages fixed top-4 right-4 z-[10000] max-w-md';
      document.body.appendChild(container);
    }
    return container;
  }

  // Показать alert
  function showAlert(content, onOk, title = 'Сообщение') {
    if (!alertModal || !alertMsgEl) {
      const text = typeof content === 'string' ? content : content.outerHTML || String(content);
      alert(text);
      if (onOk) onOk();
      return;
    }

    alertTitle.textContent = title;
    if (typeof content === 'string') {
      alertMsgEl.innerHTML = content;
    } else {
      alertMsgEl.innerHTML = '';
      alertMsgEl.appendChild(content);
    }

    window.modalManager.open('alert-modal');

    const okBtn = alertModal.querySelector('[data-close="alert"]');
    const handleOk = () => {
      window.modalManager.close('alert-modal');
      if (onOk) onOk();
      okBtn.removeEventListener('click', handleOk);
    };

    if (okBtn) {
      okBtn.addEventListener('click', handleOk);
    }
  }

  // Создание HTML результатов загрузки
  function createUploadResultsHTML(sum, results) {
    const container = document.createElement('div');
    container.className = 'space-y-4';

    const summary = document.createElement('div');
    summary.className = `p-3 rounded-lg border-l-4 ${sum.errors > 0 ? 'bg-red-900/20 border-red-600' : 'bg-blue-900/20 border-blue-600'}`;
    summary.innerHTML = `<p class="m-0 font-medium text-sm text-gray-200">Загружено: ${sum.success || 0} из ${sum.total || 0}${sum.errors > 0 ? `. Ошибок: ${sum.errors}` : ''}</p>`;
    container.appendChild(summary);

    if (results.length > 0) {
      const resultsList = document.createElement('ul');
      resultsList.className = 'space-y-2 list-none p-0 m-0';

      results.forEach(result => {
        const item = document.createElement('li');
        item.className = `p-3 rounded-lg border ${result.ok ? 'bg-green-900/20 border-green-700' : 'bg-red-900/20 border-red-700'}`;

        const header = document.createElement('div');
        header.className = 'flex items-center gap-2 mb-2';

        const icon = document.createElement('span');
        icon.className = `flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full text-xs font-bold ${result.ok ? 'bg-green-700/30 text-green-400' : 'bg-red-700/30 text-red-400'}`;
        icon.textContent = result.ok ? '✓' : '✕';

        const filename = document.createElement('span');
        filename.className = 'flex-1 font-medium text-sm text-gray-200 break-words';
        filename.textContent = result.file || 'Неизвестный файл';

        header.appendChild(icon);
        header.appendChild(filename);
        item.appendChild(header);

        if (!result.ok && result.error) {
          const errorMsg = document.createElement('p');
          errorMsg.className = 'm-0 p-2 bg-black/20 rounded text-xs text-red-300 leading-relaxed';
          errorMsg.textContent = result.error;
          item.appendChild(errorMsg);
        }

        resultsList.appendChild(item);
      });

      container.appendChild(resultsList);
    }

    return container;
  }

  // Обработка отправки формы
  uploadForm.addEventListener('submit', function (e) {
    e.preventDefault();

    if (!selectedFiles.length) {
      showMessage('Выберите файлы для загрузки', 'error');
      return;
    }
    if (selectedFiles.length > MAX_FILES) {
      showMessage(`Можно загрузить не более ${MAX_FILES} файлов за один раз.`, 'error');
      return;
    }

    const fd = new FormData();
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrf) fd.append('csrfmiddlewaretoken', csrf.value);

    selectedFiles.forEach(item => fd.append('files', item.file));
    selectedFiles.forEach(item => fd.append('descriptions', (item.desc || '').trim()));

    submitBtn && (submitBtn.disabled = true);
    setStatus('Загрузка...', true);
    setProgress(0);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', uploadForm.action, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

    xhr.upload.onprogress = function (evt) {
      if (evt.lengthComputable) {
        const pct = Math.min(100, Math.round((evt.loaded / evt.total) * 100));
        setProgress(pct);
      }
    };

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== XMLHttpRequest.DONE) return;

      setStatus('Загрузить файлы', false);
      submitBtn && (submitBtn.disabled = false);

      let data = {};
      try {
        data = JSON.parse(xhr.responseText || '{}');
      } catch (err) {
        showAlert('Ошибка обработки ответа сервера', null, 'Ошибка');
        return;
      }

      if (!(xhr.status >= 200 && xhr.status < 300) || data.success === false) {
        const err = data.error || `Ошибка сервера (${xhr.status})`;
        showAlert(err, null, 'Ошибка загрузки');
        return;
      }

      const sum = data.summary || {};
      const results = Array.isArray(data.results) ? data.results : [];

      if (sum.errors > 0) {
        const resultsHTML = createUploadResultsHTML(sum, results);
        showAlert(resultsHTML, () => {
          if (data.redirect_url) {
            window.location.href = data.redirect_url;
          }
        }, 'Результат загрузки');
      } else {
        window.modalManager.close('upload-modal');
        if (data.redirect_url) {
          window.location.href = data.redirect_url;
        }
      }
    };

    xhr.onerror = function () {
      setStatus('Загрузить файлы', false);
      submitBtn && (submitBtn.disabled = false);
      showAlert('Сетевая ошибка при загрузке. Проверьте подключение к интернету и попробуйте снова.', null, 'Ошибка сети');
    };

    xhr.send(fd);
  });
});



// // static/js/upload-modal.js
// document.addEventListener('DOMContentLoaded', function () {
//   if (window.__uploadModalInitialized__) return;
//   window.__uploadModalInitialized__ = true;
//
//   const MAX_FILES = 5;
//
//   const uploadBtn    = document.getElementById('upload-replay-btn');
//   const modal        = document.getElementById('upload-modal');
//   const modalOverlay = document.getElementById('modal-overlay');
//   const modalClose   = document.getElementById('modal-close');
//   const uploadForm   = document.getElementById('upload-form');
//   const uploadArea   = document.getElementById('upload-area');
//   const fileInput    = document.getElementById('file-input');
//   const selectedBox  = document.getElementById('selected-file');
//   const fileInfo     = document.getElementById('file-info');
//   const cancelBtn    = document.getElementById('cancel-upload');
//   const submitBtn    = document.getElementById('submit-upload');
//   const uploadStatus = document.querySelector('.upload-status');
//   const uploadText   = document.querySelector('.upload-text');
//
//   const alertModal   = document.getElementById('alert-modal');
//   const alertMsgEl   = document.getElementById('alert-message');
//   const alertTitle   = document.getElementById('alert-title');
//
//   if (!modal || !uploadForm) return;
//
//   // === АЛЕРТ-МОДАЛКА ===
//   function openAlert() {
//     if (!alertModal) return;
//     alertModal.setAttribute('aria-hidden', 'false');
//     alertModal.style.display = 'flex';
//     alertModal.style.visibility = 'visible';
//     alertModal.style.opacity = '1';
//     alertModal.style.zIndex = '9999';
//     document.body.style.overflow = 'hidden';
//   }
//
//   function closeAlert() {
//     if (!alertModal) return;
//     alertModal.setAttribute('aria-hidden', 'true');
//     alertModal.style.display = 'none';
//     alertModal.style.visibility = 'hidden';
//     alertModal.style.opacity = '0';
//     document.body.style.overflow = '';
//   }
//
//   function showAlert(content, onOk, title = 'Сообщение') {
//     if (!alertModal || !alertMsgEl) {
//       ensureMessagesContainer();
//       const text = typeof content === 'string' ? content : 'Произошла ошибка';
//       showMessage(text, 'error');
//       if (typeof onOk === 'function') onOk();
//       return;
//     }
//
//     if (alertTitle) {
//       alertTitle.textContent = title;
//     }
//
//     alertMsgEl.innerHTML = '';
//     if (typeof content === 'string') {
//       alertMsgEl.innerHTML = `<div class="alert-simple-message">${escapeHtml(content)}</div>`;
//     } else if (content instanceof HTMLElement) {
//       alertMsgEl.appendChild(content);
//     } else {
//       alertMsgEl.innerHTML = '<div class="alert-simple-message">Произошла ошибка</div>';
//     }
//
//     const handler = (e) => {
//       if (e.target && e.target.dataset && e.target.dataset.close === 'alert') {
//         alertModal.removeEventListener('click', handler);
//         closeAlert();
//         if (typeof onOk === 'function') onOk();
//       }
//     };
//     alertModal.addEventListener('click', handler);
//     openAlert();
//   }
//
//   function createUploadResultsHTML(summary, results) {
//     const container = document.createElement('div');
//
//     const summaryDiv = document.createElement('div');
//     summaryDiv.className = `alert-summary${summary.errors > 0 ? ' has-errors' : ''}`;
//
//     const summaryText = document.createElement('p');
//     summaryText.className = 'alert-summary-text';
//
//     if (summary.errors === 0) {
//       summaryText.textContent = `✓ Успешно загружено: ${summary.created} из ${summary.processed}`;
//     } else if (summary.created === 0) {
//       summaryText.textContent = `✕ Не удалось загрузить ни одного файла (ошибок: ${summary.errors})`;
//     } else {
//       summaryText.textContent = `⚠ Загружено с ошибками: ${summary.created} успешно, ${summary.errors} ошибок из ${summary.processed}`;
//     }
//
//     summaryDiv.appendChild(summaryText);
//     container.appendChild(summaryDiv);
//
//     if (summary.errors > 0 && Array.isArray(results) && results.length > 0) {
//       const resultsList = document.createElement('ul');
//       resultsList.className = 'upload-results-list';
//
//       results.forEach(result => {
//         const item = document.createElement('li');
//         item.className = `upload-result-item ${result.ok ? 'success' : 'error'}`;
//
//         const header = document.createElement('div');
//         header.className = 'upload-result-header';
//
//         const icon = document.createElement('span');
//         icon.className = `upload-result-icon status-icon-${result.ok ? 'success' : 'error'}`;
//         icon.setAttribute('aria-hidden', 'true');
//
//         const filename = document.createElement('span');
//         filename.className = 'upload-result-filename';
//         filename.textContent = result.file || 'Неизвестный файл';
//
//         header.appendChild(icon);
//         header.appendChild(filename);
//         item.appendChild(header);
//
//         if (!result.ok && result.error) {
//           const errorMsg = document.createElement('p');
//           errorMsg.className = 'upload-result-error';
//           errorMsg.textContent = result.error;
//           item.appendChild(errorMsg);
//         }
//
//         resultsList.appendChild(item);
//       });
//
//       container.appendChild(resultsList);
//     }
//
//     return container;
//   }
//
//   if (uploadText) {
//     let note = uploadText.querySelector('.upload-note');
//     if (!note) {
//       note = document.createElement('div');
//       note.className = 'upload-note';
//       note.style.opacity = '0.8';
//       note.style.fontSize = '12px';
//       note.style.marginTop = '6px';
//       note.textContent = `За один раз можно добавить не более ${MAX_FILES} файлов. Для каждого файла можно указать своё описание.`;
//       uploadText.appendChild(note);
//     }
//   }
//
//   let selectedFiles = [];
//   let isFileDialogOpen = false;
//
//   function openModal() {
//     modal.classList.add('active');
//     modal.setAttribute('aria-hidden', 'false');
//     document.body.style.overflow = 'hidden';
//   }
//
//   function closeModal() {
//     modal.classList.remove('active');
//     modal.setAttribute('aria-hidden', 'true');
//     document.body.style.overflow = '';
//     resetForm();
//   }
//
//   function resetForm() {
//     selectedFiles = [];
//     if (fileInput) fileInput.value = '';
//     if (fileInfo) fileInfo.innerHTML = '';
//     if (selectedBox) selectedBox.style.display = 'none';
//     if (submitBtn) submitBtn.disabled = true;
//     setStatus('Загрузить файлы', false);
//   }
//
//   function setStatus(text, loading=false) {
//     if (!uploadStatus) return;
//     uploadStatus.innerHTML = loading ? `<span class="upload-spinner"></span>${text}` : text;
//   }
//
//   function ensureMessagesContainer() {
//     let container = document.querySelector('.messages');
//     if (!container) {
//       container = document.createElement('div');
//       container.className = 'messages';
//       const contentDiv = document.querySelector('#content .container') || document.body;
//       contentDiv.insertBefore(container, contentDiv.firstChild);
//     }
//     return container;
//   }
//
//   function showMessage(text, type='info') {
//     const container = ensureMessagesContainer();
//     const el = document.createElement('div');
//     el.className = `message message--${type}`;
//     el.textContent = text;
//     container.appendChild(el);
//     setTimeout(() => el.remove(), 5000);
//   }
//
//   function validateFile(file) {
//     if (!file.name.toLowerCase().endsWith('.mtreplay')) {
//       showMessage(`«${file.name}» — не .mtreplay`, 'error');
//       return false;
//     }
//     if (file.size > 50 * 1024 * 1024) {
//       showMessage(`«${file.name}» — больше 50MB`, 'error');
//       return false;
//     }
//     return true;
//   }
//
//   function fmtBytes(bytes) {
//     if (bytes === 0) return '0 B';
//     const k = 1024, sizes = ['B','KB','MB','GB','TB'];
//     const i = Math.floor(Math.log(bytes)/Math.log(k));
//     return `${(bytes/Math.pow(k,i)).toFixed(2)} ${sizes[i]}`;
//   }
//
//   function renderSelected() {
//     if (!fileInfo || !selectedBox) return;
//     if (selectedFiles.length === 0) {
//       selectedBox.style.display = 'none';
//       if (submitBtn) submitBtn.disabled = true;
//       return;
//     }
//     selectedBox.style.display = 'block';
//     if (submitBtn) submitBtn.disabled = false;
//
//     const total = selectedFiles.reduce((s, item)=> s + item.file.size, 0);
//     const left = Math.max(0, MAX_FILES - selectedFiles.length);
//     fileInfo.innerHTML = `
//       <div class="file-total">
//         Выбрано: ${selectedFiles.length}/${MAX_FILES}${left ? ` (можно добавить ещё ${left})` : ''} • ${fmtBytes(total)}
//       </div>
//       <div class="file-list">
//         ${selectedFiles.map((item,i)=>`
//           <div class="file-row" data-idx="${i}">
//             <span class="file-name" title="${escapeHtml(item.file.name)}">${escapeHtml(item.file.name)}</span>
//             <span class="file-size">${fmtBytes(item.file.size)}</span>
//             <button type="button" class="file-remove" aria-label="Удалить" data-remove="${i}">✕</button>
//           </div>
//           <div class="file-desc">
//             <input type="text"
//                    class="file-desc-input"
//                    data-desc-idx="${i}"
//                    maxlength="60"
//                    placeholder="Короткое описание(60 символов)"
//                    style="width:100%; padding:8px; border-radius:8px; border:1px solid #2b2c3c; background:#0f1018; color:#ddd;"
//                    value="${escapeHtml(item.desc || '')}">
//           </div>
//         `).join('')}
//       </div>
//
//       <div id="upload-progress" class="upload-progress" style="display:none">
//         <div class="bar"></div>
//         <span class="label">0%</span>
//       </div>
//     `;
//   }
//
//   function escapeHtml(s) {
//     return String(s).replace(/[&<>"']/g, ch => ({
//       '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
//     }[ch]));
//   }
//
//   function addFiles(list) {
//     if (selectedFiles.length >= MAX_FILES) {
//       showMessage(`Лимит ${MAX_FILES} файлов за один раз. Удалите лишний файл, чтобы добавить новый.`, 'error');
//       return;
//     }
//     const remaining = MAX_FILES - selectedFiles.length;
//     const filesArr = Array.from(list);
//     let added = 0;
//
//     for (const f of filesArr) {
//       if (added >= remaining) break;
//       if (!validateFile(f)) continue;
//       if (!selectedFiles.find(x => x.file.name === f.name && x.file.size === f.size)) {
//         selectedFiles.push({ file: f, desc: '' });
//         added += 1;
//       }
//     }
//
//     if (filesArr.length > added) {
//       showMessage(`Можно добавить не более ${MAX_FILES} файлов. Добавлены только первые ${added} из ${filesArr.length}.`, 'error');
//     }
//
//     renderSelected();
//   }
//
//   function removeAt(idx) {
//     selectedFiles.splice(idx, 1);
//     renderSelected();
//   }
//
//   function setProgress(pct) {
//     const box = document.getElementById('upload-progress');
//     if (!box) return;
//     const bar = box.querySelector('.bar');
//     const lbl = box.querySelector('.label');
//     box.style.display = 'block';
//     bar.style.width = `${pct}%`;
//     lbl.textContent = `${pct}%`;
//   }
//
//   function openFilePickerOnce() {
//     if (!fileInput) return;
//     if (isFileDialogOpen) return;
//
//     isFileDialogOpen = true;
//     fileInput.value = '';
//     fileInput.click();
//
//     const release = () => {
//       isFileDialogOpen = false;
//       window.removeEventListener('focus', release, true);
//       fileInput.removeEventListener('change', release);
//     };
//     window.addEventListener('focus', release, true);
//     fileInput.addEventListener('change', release, { once: true });
//   }
//
//   if (uploadBtn) {
//     uploadBtn.addEventListener('click', (e)=>{ e.preventDefault(); openModal(); });
//   }
//   modalClose && modalClose.addEventListener('click', (e)=>{ e.preventDefault(); closeModal(); });
//   cancelBtn && cancelBtn.addEventListener('click', (e)=>{ e.preventDefault(); closeModal(); });
//   modalOverlay && modalOverlay.addEventListener('click', (e)=>{ if (e.target === modalOverlay) closeModal(); });
//   document.addEventListener('keydown', (e)=>{
//     if (e.key === 'Escape' && (modal.classList.contains('active') || modal.getAttribute('aria-hidden') === 'false')) {
//       closeModal();
//     }
//   });
//
//   fileInput && fileInput.addEventListener('click', (e) => e.stopPropagation());
//   uploadArea && uploadArea.addEventListener('click', (e) => { e.preventDefault(); openFilePickerOnce(); });
//
//   fileInput && fileInput.addEventListener('change', (e) => {
//     const files = e.target.files;
//     if (files && files.length) addFiles(files);
//   });
//
//   ['dragenter','dragover','dragleave','drop'].forEach(ev =>
//     uploadArea && uploadArea.addEventListener(ev, (e)=>{ e.preventDefault(); e.stopPropagation(); })
//   );
//   uploadArea && uploadArea.addEventListener('dragover', ()=> uploadArea.classList.add('dragover'));
//   uploadArea && uploadArea.addEventListener('dragleave', ()=> uploadArea.classList.remove('dragover'));
//   uploadArea && uploadArea.addEventListener('drop', (e) => {
//     uploadArea.classList.remove('dragover');
//     const files = e.dataTransfer && e.dataTransfer.files;
//     if (files && files.length) addFiles(files);
//   });
//
//   ['dragenter','dragover','dragleave','drop'].forEach(ev =>
//     document.addEventListener(ev, (e)=>{ e.preventDefault(); e.stopPropagation(); })
//   );
//
//   fileInfo && fileInfo.addEventListener('click', (e) => {
//     const idx = e.target.getAttribute && e.target.getAttribute('data-remove');
//     if (idx !== null && idx !== undefined) removeAt(parseInt(idx, 10));
//   });
//
//   fileInfo && fileInfo.addEventListener('input', (e) => {
//     const input = e.target.closest && e.target.closest('.file-desc-input');
//     if (!input) return;
//     const idxStr = input.getAttribute('data-desc-idx');
//     if (idxStr === null || idxStr === undefined) return;
//     const idx = parseInt(idxStr, 10);
//     if (!Number.isInteger(idx) || idx < 0 || idx >= selectedFiles.length) return;
//     selectedFiles[idx].desc = input.value.slice(0, 60);
//   });
//
//   uploadForm.addEventListener('submit', function (e) {
//     e.preventDefault();
//
//     if (!selectedFiles.length) {
//       showMessage('Выберите файлы для загрузки', 'error');
//       return;
//     }
//     if (selectedFiles.length > MAX_FILES) {
//       showMessage(`Можно загрузить не более ${MAX_FILES} файлов за один раз.`, 'error');
//       return;
//     }
//
//     const fd = new FormData();
//     const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
//     if (csrf) fd.append('csrfmiddlewaretoken', csrf.value);
//
//     selectedFiles.forEach(item => fd.append('files', item.file));
//     selectedFiles.forEach(item => fd.append('descriptions', (item.desc || '').trim()));
//
//     submitBtn && (submitBtn.disabled = true);
//     setStatus('Загрузка...', true);
//     setProgress(0);
//
//     const xhr = new XMLHttpRequest();
//     xhr.open('POST', uploadForm.action, true);
//     xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
//
//     xhr.upload.onprogress = function (evt) {
//       if (evt.lengthComputable) {
//         const pct = Math.min(100, Math.round((evt.loaded / evt.total) * 100));
//         setProgress(pct);
//       }
//     };
//
//     xhr.onreadystatechange = function () {
//       if (xhr.readyState !== XMLHttpRequest.DONE) return;
//
//       setStatus('Загрузить файлы', false);
//       submitBtn && (submitBtn.disabled = false);
//
//       let data = {};
//       try {
//         data = JSON.parse(xhr.responseText || '{}');
//       } catch(err) {
//         showAlert('Ошибка обработки ответа сервера', null, 'Ошибка');
//         return;
//       }
//
//       if (!(xhr.status >= 200 && xhr.status < 300) || data.success === false) {
//         const err = data.error || `Ошибка сервера (${xhr.status})`;
//         showAlert(err, null, 'Ошибка загрузки');
//         return;
//       }
//
//       const sum = data.summary || {};
//       const results = Array.isArray(data.results) ? data.results : [];
//
//       if (sum.errors > 0) {
//         const resultsHTML = createUploadResultsHTML(sum, results);
//         showAlert(resultsHTML, () => {
//           if (data.redirect_url) {
//             window.location.href = data.redirect_url;
//           }
//         }, 'Результат загрузки');
//       } else {
//         closeModal();
//         if (data.redirect_url) {
//           window.location.href = data.redirect_url;
//         }
//       }
//     };
//
//     xhr.onerror = function () {
//       setStatus('Загрузить файлы', false);
//       submitBtn && (submitBtn.disabled = false);
//       showAlert('Сетевая ошибка при загрузке. Проверьте подключение к интернету и попробуйте снова.', null, 'Ошибка сети');
//     };
//
//     const p = document.getElementById('upload-progress');
//     if (p) p.style.display = 'block';
//
//     xhr.send(fd);
//   });
// });