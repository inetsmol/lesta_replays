// static/js/upload-modal.js
window.app = window.app || {};
document.addEventListener('DOMContentLoaded', function () {
  if (window.__uploadModalInitialized__) return;
  window.__uploadModalInitialized__ = true;

  const MAX_FILES = 5;

  const uploadBtn    = document.getElementById('upload-replay-btn');
  const modal        = document.getElementById('upload-modal');
  const modalOverlay = document.getElementById('modal-overlay');
  const modalClose   = document.getElementById('modal-close');
  const uploadForm   = document.getElementById('upload-form');
  const uploadArea   = document.getElementById('upload-area');
  const fileInput    = document.getElementById('file-input');
  const selectedBox  = document.getElementById('selected-file');
  const fileInfo     = document.getElementById('file-info');
  const cancelBtn    = document.getElementById('cancel-upload');
  const submitBtn    = document.getElementById('submit-upload');
  const uploadStatus = document.querySelector('.upload-status');
  const uploadText   = document.querySelector('.upload-text');

  const alertModal   = document.getElementById('alert-modal');
  const alertMsgEl   = document.getElementById('alert-message');
  const alertTitle   = document.getElementById('alert-title');
  const alertHeader  = alertModal ? alertModal.querySelector('.modal-header') : null;

  if (!modal || !uploadForm) return;

  // === АЛЕРТ-МОДАЛКА ===
  function openAlert() {
    if (!alertModal) return;
    alertModal.setAttribute('aria-hidden', 'false');
    alertModal.style.display = 'flex';
    alertModal.style.visibility = 'visible';
    alertModal.style.opacity = '1';
    alertModal.style.zIndex = '9999';
    document.body.style.overflow = 'hidden';
  }

  function closeAlert() {
    if (!alertModal) return;
    alertModal.setAttribute('aria-hidden', 'true');
    alertModal.style.display = 'none';
    alertModal.style.visibility = 'hidden';
    alertModal.style.opacity = '0';
    document.body.style.overflow = '';
  }

  function showAlert(content, onOk, title = 'Сообщение', variant = 'error') {
    if (!alertModal || !alertMsgEl) {
      ensureMessagesContainer();
      const text = typeof content === 'string' ? content : 'Произошла ошибка';
      showMessage(text, 'error');
      if (typeof onOk === 'function') onOk();
      return;
    }

    if (alertTitle && alertHeader) {
        if (title) {
            alertTitle.textContent = title;
            alertHeader.style.display = '';
        } else {
            alertTitle.textContent = '';
            alertHeader.style.display = 'none';
        }
    }

    alertMsgEl.innerHTML = '';
    if (typeof content === 'string') {
      const variants = {
        success: 'alert-simple-message--success',
        info: 'alert-simple-message--info',
        error: 'alert-simple-message--error'
      };
      const suffix = variants[variant] || variants.error;
      alertMsgEl.innerHTML = `<div class="alert-simple-message ${suffix}">${escapeHtml(content)}</div>`;
    } else if (content instanceof HTMLElement) {
      alertMsgEl.appendChild(content);
    } else {
      alertMsgEl.innerHTML = '<div class="alert-simple-message alert-simple-message--error">Произошла ошибка</div>';
    }

    const handler = (e) => {
      if (e.target && e.target.dataset && e.target.dataset.close === 'alert') {
        alertModal.removeEventListener('click', handler);
        closeAlert();
        if (typeof onOk === 'function') onOk();
      }
    };
    alertModal.addEventListener('click', handler);
    openAlert();
  }

  window.app.showAlert = showAlert;

  function createUploadResultsHTML(summary, results) {
    const container = document.createElement('div');

    const summaryDiv = document.createElement('div');
    summaryDiv.className = `alert-summary${summary.errors > 0 ? ' has-errors' : ''}`;

    const summaryText = document.createElement('p');
    summaryText.className = 'alert-summary-text';

    if (summary.errors === 0) {
      summaryText.textContent = `✓ Успешно загружено: ${summary.created} из ${summary.processed}`;
    } else if (summary.created === 0) {
      summaryText.textContent = `✕ Не удалось загрузить ни одного файла (ошибок: ${summary.errors})`;
    } else {
      summaryText.textContent = `⚠ Загружено с ошибками: ${summary.created} успешно, ${summary.errors} ошибок из ${summary.processed}`;
    }

    summaryDiv.appendChild(summaryText);
    container.appendChild(summaryDiv);

    if (summary.errors > 0 && Array.isArray(results) && results.length > 0) {
      const resultsList = document.createElement('ul');
      resultsList.className = 'upload-results-list';

      results.forEach(result => {
        const item = document.createElement('li');
        item.className = `upload-result-item ${result.ok ? 'success' : 'error'}`;

        const header = document.createElement('div');
        header.className = 'upload-result-header';

        const icon = document.createElement('span');
        icon.className = `upload-result-icon status-icon-${result.ok ? 'success' : 'error'}`;
        icon.setAttribute('aria-hidden', 'true');

        const filename = document.createElement('span');
        filename.className = 'upload-result-filename';
        filename.textContent = result.file || 'Неизвестный файл';

        header.appendChild(icon);
        header.appendChild(filename);
        item.appendChild(header);

        if (!result.ok && result.error) {
          const errorMsg = document.createElement('p');
          errorMsg.className = 'upload-result-error';
          errorMsg.textContent = result.error;
          item.appendChild(errorMsg);
        }

        resultsList.appendChild(item);
      });

      container.appendChild(resultsList);
    }

    return container;
  }

  if (uploadText) {
    let note = uploadText.querySelector('.upload-note');
    if (!note) {
      note = document.createElement('div');
      note.className = 'upload-note';
      note.style.opacity = '0.8';
      note.style.fontSize = '12px';
      note.style.marginTop = '6px';
      note.textContent = `За один раз можно добавить не более ${MAX_FILES} файлов. Для каждого файла можно указать своё описание.`;
      uploadText.appendChild(note);
    }
  }

  let selectedFiles = [];
  let isFileDialogOpen = false;

  function openModal() {
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    resetForm();
  }

  function resetForm() {
    selectedFiles = [];
    if (fileInput) fileInput.value = '';
    if (fileInfo) fileInfo.innerHTML = '';
    if (selectedBox) selectedBox.style.display = 'none';
    if (submitBtn) submitBtn.disabled = true;
    setStatus('Загрузить файлы', false);
  }

  function setStatus(text, loading=false) {
    if (!uploadStatus) return;
    uploadStatus.innerHTML = loading ? `<span class="upload-spinner"></span>${text}` : text;
  }

  function ensureMessagesContainer() {
    let container = document.querySelector('.messages');
    if (!container) {
      container = document.createElement('div');
      container.className = 'messages';
      const contentDiv = document.querySelector('#content .container') || document.body;
      contentDiv.insertBefore(container, contentDiv.firstChild);
    }
    return container;
  }

  function showMessage(text, type='info') {
    const container = ensureMessagesContainer();
    const el = document.createElement('div');
    el.className = `message message--${type}`;
    el.textContent = text;
    container.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

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



  function renderSelected() {
    if (!fileInfo || !selectedBox) return;
    if (selectedFiles.length === 0) {
      selectedBox.style.display = 'none';
      if (submitBtn) submitBtn.disabled = true;
      return;
    }
    selectedBox.style.display = 'block';
    if (submitBtn) submitBtn.disabled = false;

    const left = Math.max(0, MAX_FILES - selectedFiles.length);
    fileInfo.innerHTML = `
      <div class="file-total">
        Выбрано: ${selectedFiles.length}/${MAX_FILES}${left ? ` (можно добавить ещё ${left})` : ''}
      </div>
      <div class="file-list">
        ${selectedFiles.map((item,i)=>`
          <div class="file-row" data-idx="${i}">
            <span class="file-name" title="${escapeHtml(item.file.name)}">${escapeHtml(item.file.name)}</span>
            <button type="button" class="file-remove" aria-label="Удалить" data-remove="${i}">✕</button>
          </div>
          <div class="file-desc">
            <input type="text"
                   class="file-desc-input"
                   data-desc-idx="${i}"
                   maxlength="60"
                   placeholder="Короткое описание(60 символов)"
                   style="width:100%; padding:8px; border-radius:8px; border:1px solid #2b2c3c; background:#0f1018; color:#ddd;"
                   value="${escapeHtml(item.desc || '')}">
          </div>
        `).join('')}
      </div>

      <div id="upload-progress" class="upload-progress" style="display:none">
        <div class="bar"></div>
        <span class="label">0%</span>
      </div>
    `;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[ch]));
  }

  function formatFilesLabel(count) {
    const n = Math.abs(count);
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `${count} файл`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${count} файла`;
    return `${count} файлов`;
  }

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

  function removeAt(idx) {
    selectedFiles.splice(idx, 1);
    renderSelected();
  }

  function setProgress(pct) {
    const box = document.getElementById('upload-progress');
    if (!box) return;
    const bar = box.querySelector('.bar');
    const lbl = box.querySelector('.label');
    box.style.display = 'block';
    bar.style.width = `${pct}%`;
    lbl.textContent = `${pct}%`;
  }

  function openFilePickerOnce() {
    if (!fileInput) return;
    if (isFileDialogOpen) return;

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

  if (uploadBtn) {
    uploadBtn.addEventListener('click', (e)=>{ e.preventDefault(); openModal(); });
  }
  modalClose && modalClose.addEventListener('click', (e)=>{ e.preventDefault(); closeModal(); });
  cancelBtn && cancelBtn.addEventListener('click', (e)=>{ e.preventDefault(); closeModal(); });
  modalOverlay && modalOverlay.addEventListener('click', (e)=>{ if (e.target === modalOverlay) closeModal(); });
  document.addEventListener('keydown', (e)=>{
    if (e.key === 'Escape' && (modal.classList.contains('active') || modal.getAttribute('aria-hidden') === 'false')) {
      closeModal();
    }
  });

  fileInput && fileInput.addEventListener('click', (e) => e.stopPropagation());
  uploadArea && uploadArea.addEventListener('click', (e) => { e.preventDefault(); openFilePickerOnce(); });

  fileInput && fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files && files.length) addFiles(files);
  });

  ['dragenter','dragover','dragleave','drop'].forEach(ev =>
    uploadArea && uploadArea.addEventListener(ev, (e)=>{ e.preventDefault(); e.stopPropagation(); })
  );
  uploadArea && uploadArea.addEventListener('dragover', ()=> uploadArea.classList.add('dragover'));
  uploadArea && uploadArea.addEventListener('dragleave', ()=> uploadArea.classList.remove('dragover'));
  uploadArea && uploadArea.addEventListener('drop', (e) => {
    uploadArea.classList.remove('dragover');
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) addFiles(files);
  });

  ['dragenter','dragover','dragleave','drop'].forEach(ev =>
    document.addEventListener(ev, (e)=>{ e.preventDefault(); e.stopPropagation(); })
  );

  fileInfo && fileInfo.addEventListener('click', (e) => {
    const idx = e.target.getAttribute && e.target.getAttribute('data-remove');
    if (idx !== null && idx !== undefined) removeAt(parseInt(idx, 10));
  });

  fileInfo && fileInfo.addEventListener('input', (e) => {
    const input = e.target.closest && e.target.closest('.file-desc-input');
    if (!input) return;
    const idxStr = input.getAttribute('data-desc-idx');
    if (idxStr === null || idxStr === undefined) return;
    const idx = parseInt(idxStr, 10);
    if (!Number.isInteger(idx) || idx < 0 || idx >= selectedFiles.length) return;
    selectedFiles[idx].desc = input.value.slice(0, 60);
  });

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
      } catch(err) {
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
      const initialSelectedCount = selectedFiles.length;

      if (sum.errors > 0) {
        const resultsHTML = createUploadResultsHTML(sum, results);
        showAlert(resultsHTML, () => {
          if (data.redirect_url) {
            window.location.href = data.redirect_url;
          }
        }, 'Результат загрузки');
      } else {
        const createdRaw = Number(sum.created);
        const processedRaw = Number(sum.processed);
        const successCount = Number.isFinite(createdRaw) ? Math.max(0, Math.round(createdRaw)) : initialSelectedCount;
        const processedCount = Number.isFinite(processedRaw) ? Math.max(0, Math.round(processedRaw)) : successCount;
        const effectiveCount = processedCount || successCount || initialSelectedCount;
        const shouldShowSuccessAlert = effectiveCount > 1;
        closeModal();
        if (shouldShowSuccessAlert) {
          const onOk = () => {
            if (data.redirect_url) {
              window.location.href = data.redirect_url;
            }
          };
          const message = `Все ${formatFilesLabel(effectiveCount)} успешно загружены.`;
          showAlert(message, onOk, 'Загрузка завершена', 'success');
        } else if (data.redirect_url) {
          window.location.href = data.redirect_url;
        }
      }
    };

    xhr.onerror = function () {
      setStatus('Загрузить файлы', false);
      submitBtn && (submitBtn.disabled = false);
      showAlert('Сетевая ошибка при загрузке. Проверьте подключение к интернету и попробуйте снова.', null, 'Ошибка сети');
    };

    const p = document.getElementById('upload-progress');
    if (p) p.style.display = 'block';

    xhr.send(fd);
  });
});
