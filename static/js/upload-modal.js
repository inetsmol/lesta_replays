// static/js/upload-modal.js
document.addEventListener('DOMContentLoaded', function () {
    // === Защита от повторной инициализации (если скрипт подключили дважды) ===
    if (window.__uploadModalInitialized__) {
        console.warn('upload-modal.js: already initialized — skipping duplicate init');
        return;
    }
    window.__uploadModalInitialized__ = true;

    console.log('Upload modal script loaded');

    // === Элементы ===
    const uploadBtn    = document.getElementById('upload-replay-btn');
    const modal        = document.getElementById('upload-modal');
    const modalOverlay = document.getElementById('modal-overlay');
    const modalClose   = document.getElementById('modal-close');
    const uploadForm   = document.getElementById('upload-form');
    const uploadArea   = document.getElementById('upload-area');
    const fileInput    = document.getElementById('file-input');
    const selectedFile = document.getElementById('selected-file');
    const fileInfo     = document.getElementById('file-info');
    const cancelBtn    = document.getElementById('cancel-upload');
    const submitBtn    = document.getElementById('submit-upload');
    const uploadStatus = document.querySelector('.upload-status');

    if (!uploadBtn || !modal) {
        console.error('Upload button or modal not found');
        return;
    }

    let currentFile = null;

    // === Управление модальным окном ===
    function openModal() {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
        resetForm();
    }

    function resetForm() {
        currentFile = null;
        if (fileInput) fileInput.value = '';
        if (selectedFile) selectedFile.style.display = 'none';
        if (fileInfo) fileInfo.innerHTML = '';
        if (submitBtn) submitBtn.disabled = true;
        updateUploadStatus('Загрузить файл', false);
    }

    function updateUploadStatus(text, loading = false) {
        if (!uploadStatus) return;
        uploadStatus.innerHTML = loading
            ? `<span class="upload-spinner"></span>${text}`
            : text;
    }

    // === Валидация файла ===
    function validateFile(file) {
        const maxSize = 50 * 1024 * 1024; // 50MB
        const allowedExtensions = ['.mtreplay'];
        const dot = file.name.lastIndexOf('.');
        const fileExtension = dot >= 0 ? file.name.toLowerCase().slice(dot) : '';

        if (!allowedExtensions.includes(fileExtension)) {
            showMessage('Файл имеет неподдерживаемый формат. Разрешены только .mtreplay файлы.', 'error');
            return false;
        }
        if (file.size > maxSize) {
            showMessage('Файл слишком большой. Максимальный размер: 50MB.', 'error');
            return false;
        }
        return true;
    }

    // === Сообщения ===
    function createMessagesContainer() {
        const container = document.createElement('div');
        container.className = 'messages';
        const contentDiv = document.querySelector('#content .container') || document.body;
        contentDiv.insertBefore(container, contentDiv.firstChild);
        return container;
    }

    function showMessage(text, type = 'info') {
        const messagesContainer = document.querySelector('.messages') || createMessagesContainer();
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message--${type}`;
        messageDiv.textContent = text;
        messagesContainer.appendChild(messageDiv);
        setTimeout(() => messageDiv.remove(), 5000);
    }

    // === Обновление информации о файле ===
    function updateFileInfo() {
        if (!selectedFile || !fileInfo) return;

        if (!currentFile) {
            selectedFile.style.display = 'none';
            if (submitBtn) submitBtn.disabled = true;
            return;
        }

        selectedFile.style.display = 'block';
        if (submitBtn) submitBtn.disabled = false;

        // передаём event, чтобы остановить всплытие и не открыть диалог
        fileInfo.innerHTML = `
            <div class="file-icon">📄</div>
            <div class="file-details">
                <div class="file-name">${currentFile.name}</div>
                <div class="file-size">${formatFileSize(currentFile.size)}</div>
            </div>
            <button type="button" class="file-remove" onclick="removeCurrentFile(event)">✕</button>
        `;
    }

    // Глобальная функция для удаления файла (нужна для inline-обработчика)
    window.removeCurrentFile = function (e) {
        // не даём клику по ✕ всплыть до uploadArea и открыть диалог выбора файла
        if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
        currentFile = null;
        updateFileInfo();
    };

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    }

    function handleFile(file) {
        if (validateFile(file)) {
            currentFile = file;
            updateFileInfo();
            showMessage(`Файл выбран: ${file.name}`, 'success');
        }
    }

    // === «Замок» на открытие диалога выбора файла (исправляет множественное открытие) ===
    let isFileDialogOpen = false;

    function openFilePickerOnce() {
        // если диалог уже открыт — выходим
        if (isFileDialogOpen) return;

        isFileDialogOpen = true;

        // очищаем value, чтобы повторный выбор того же файла сработал
        if (fileInput) fileInput.value = '';
        fileInput.click();

        // снимаем «замок», когда окно выбора файла закрылось или файл выбран
        const release = () => {
            isFileDialogOpen = false;
            window.removeEventListener('focus', release, true);
            fileInput.removeEventListener('change', release);
        };

        // когда диалог закрывается, фокус возвращается окну
        window.addEventListener('focus', release, true);
        // либо файл выбран
        fileInput.addEventListener('change', release, { once: true });
    }

    // === События ===
    uploadBtn.addEventListener('click', function (e) {
        e.preventDefault();
        openModal();
    });

    if (modalClose) {
        modalClose.addEventListener('click', function (e) {
            e.preventDefault();
            closeModal();
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function (e) {
            e.preventDefault();
            closeModal();
        });
    }

    if (modalOverlay) {
        modalOverlay.addEventListener('click', function (e) {
            if (e.target === modalOverlay) closeModal();
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) closeModal();
    });

    // выбор файла через input
    if (fileInput) {
        fileInput.addEventListener('change', function (e) {
            // если пользователь закрыл диалог без выбора — файлов нет
            if (!e.target.files || e.target.files.length === 0) return;
            handleFile(e.target.files[0]);
        });

        // на всякий случай: не даём клику по самому input всплыть
        fileInput.addEventListener('click', (e) => e.stopPropagation());
    }

    // клик по области загрузки — открываем диалог один раз
    if (uploadArea) {
        uploadArea.addEventListener('click', function (e) {
            // если клик по кнопке удаления (или её дочерним элементам) — ничего не делаем
            if (e.target.closest && e.target.closest('.file-remove')) return;
            if (!fileInput) return;
            openFilePickerOnce();
        });

        // Drag & Drop
        let dragCounter = 0;

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev =>
            uploadArea.addEventListener(ev, (e) => e.preventDefault())
        );

        uploadArea.addEventListener('dragenter', function () {
            dragCounter++;
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', function () {
            dragCounter--;
            if (dragCounter <= 0) {
                dragCounter = 0;
                uploadArea.classList.remove('dragover');
            }
        });

        uploadArea.addEventListener('drop', function (e) {
            dragCounter = 0;
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer?.files;
            if (files && files.length > 0) handleFile(files[0]);
        });
    }

    // отправка формы
    if (uploadForm) {
        uploadForm.addEventListener('submit', function (e) {
            e.preventDefault();

            if (!currentFile) {
                showMessage('Выберите файл для загрузки', 'error');
                return;
            }

            const formData = new FormData();
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfToken) formData.append('csrfmiddlewaretoken', csrfToken.value);
            formData.append('file', currentFile);

            if (submitBtn) submitBtn.disabled = true;
            updateUploadStatus('Загрузка...', true);

            fetch(uploadForm.action, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
.then(response => {
    // Сначала проверяем статус ответа
    if (!response.ok) {
        return response.json().then(data => {
            throw new Error(data.error || 'Ошибка сервера');
        });
    }

    // Если это редирект
    if (response.redirected) {
        window.location.href = response.url;
        return null;
    }

    // Если это JSON ответ
    return response.json();
})
    .then(data => {
        if (data === null) return; // Редирект уже произошел

        if (data.success) {
            showMessage(data.message, 'success');
            closeModal();
            if (data.redirect_url) {
                window.location.href = data.redirect_url;
            }
        } else {
            showMessage(data.error, 'error');
            closeModal();
            if (data.redirect_url) {
                setTimeout(() => {
                    window.location.href = data.redirect_url;
                }, 2000); // Даем время показать сообщение
            }
        }
    })
    .catch(error => {
        console.error('Ошибка загрузки:', error);
        showMessage(error.message || 'Произошла ошибка при загрузке файла', 'error');
        closeModal();
        setTimeout(() => {
            window.location.href = '/'; // Переход к списку
        }, 2000);
    })
    .finally(() => {
        updateUploadStatus('Загрузить файл', false);
        if (submitBtn) submitBtn.disabled = false;
    });
        });
    }

    // Глобально предотвращаем drag&drop по всей странице
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, function (e) {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    console.log('Upload modal initialized successfully');
});
