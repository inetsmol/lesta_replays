// static/js/upload-modal.js
document.addEventListener('DOMContentLoaded', function() {
    // Элементы
    const uploadBtn = document.getElementById('upload-replay-btn');
    const modal = document.getElementById('upload-modal');
    const modalOverlay = document.getElementById('modal-overlay');
    const modalClose = document.getElementById('modal-close');
    const uploadForm = document.getElementById('upload-form');
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    const selectedFiles = document.getElementById('selected-files');
    const filesList = document.getElementById('files-list');
    const cancelBtn = document.getElementById('cancel-upload');
    const submitBtn = document.getElementById('submit-upload');
    const uploadStatus = document.querySelector('.upload-status');

    let selectedFilesArray = [];

    // Открытие модального окна
    function openModal() {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    // Закрытие модального окна
    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
        resetForm();
    }

    // Сброс формы
    function resetForm() {
        selectedFilesArray = [];
        fileInput.value = '';
        selectedFiles.style.display = 'none';
        filesList.innerHTML = '';
        submitBtn.disabled = true;
        updateUploadStatus('Загрузить файлы', false);
    }

    // Обновление статуса кнопки загрузки
    function updateUploadStatus(text, loading = false) {
        uploadStatus.innerHTML = loading
            ? `<span class="upload-spinner"></span>${text}`
            : text;
    }

    // Валидация файлов
    function validateFiles(files) {
        const validFiles = [];
        const maxSize = 50 * 1024 * 1024; // 50MB
        const allowedExtensions = ['.mtreplay'];

        Array.from(files).forEach(file => {
            const fileExtension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));

            if (!allowedExtensions.includes(fileExtension)) {
                showMessage(`Файл ${file.name} имеет неподдерживаемый формат. Разрешены только .mtreplay файлы.`, 'error');
                return;
            }

            if (file.size > maxSize) {
                showMessage(`Файл ${file.name} слишком большой. Максимальный размер: 50MB.`, 'error');
                return;
            }

            // Проверка на дубликаты
            if (selectedFilesArray.some(f => f.name === file.name && f.size === file.size)) {
                showMessage(`Файл ${file.name} уже выбран.`, 'warning');
                return;
            }

            validFiles.push(file);
        });

        return validFiles;
    }

    // Показ сообщений (интеграция с Django messages)
    function showMessage(text, type = 'info') {
        // Создаем временное сообщение в стиле Django
        const messagesContainer = document.querySelector('.messages') || createMessagesContainer();
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message--${type}`;
        messageDiv.textContent = text;

        messagesContainer.appendChild(messageDiv);

        // Автоматическое удаление через 5 секунд
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.remove();
            }
        }, 5000);
    }

    // Создание контейнера для сообщений если его нет
    function createMessagesContainer() {
        const container = document.createElement('div');
        container.className = 'messages';
        const contentDiv = document.querySelector('#content .container');
        contentDiv.insertBefore(container, contentDiv.firstChild);
        return container;
    }

    // Обновление списка файлов
    function updateFilesList() {
        filesList.innerHTML = '';

        if (selectedFilesArray.length === 0) {
            selectedFiles.style.display = 'none';
            submitBtn.disabled = true;
            return;
        }

        selectedFiles.style.display = 'block';
        submitBtn.disabled = false;

        selectedFilesArray.forEach((file, index) => {
            const li = document.createElement('li');
            li.innerHTML = `
                <span>${file.name}</span>
                <small style="color: var(--muted); margin-left: auto;">
                    ${formatFileSize(file.size)}
                </small>
                <button type="button" class="remove-file" data-index="${index}" style="
                    background: none; border: none; color: var(--accent); 
                    cursor: pointer; padding: 2px 6px; border-radius: 4px;
                    margin-left: 8px; font-size: 12px;
                ">✕</button>
            `;
            filesList.appendChild(li);
        });

        // Обработчики удаления файлов
        document.querySelectorAll('.remove-file').forEach(btn => {
            btn.addEventListener('click', function() {
                const index = parseInt(this.dataset.index);
                selectedFilesArray.splice(index, 1);
                updateFilesList();
            });
        });
    }

    // Форматирование размера файла
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Обработка выбора файлов
    function handleFiles(files) {
        const validFiles = validateFiles(files);
        selectedFilesArray.push(...validFiles);
        updateFilesList();

        if (validFiles.length > 0) {
            showMessage(`Выбрано файлов: ${validFiles.length}`, 'success');
        }
    }

    // События для открытия/закрытия модального окна
    uploadBtn.addEventListener('click', openModal);
    modalClose.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', closeModal);

    // Закрытие по Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });

    // Обработка выбора файлов через input
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleFiles(e.target.files);
        }
    });

    // Обработка клика по области загрузки
    uploadArea.addEventListener('click', function() {
        fileInput.click();
    });

    // Drag & Drop функционал
    let dragCounter = 0;

    uploadArea.addEventListener('dragenter', function(e) {
        e.preventDefault();
        dragCounter++;
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            uploadArea.classList.remove('dragover');
        }
    });

    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
    });

    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        dragCounter = 0;
        uploadArea.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFiles(files);
        }
    });

    // Обработка отправки формы
    uploadForm.addEventListener('submit', function(e) {
        e.preventDefault();

        if (selectedFilesArray.length === 0) {
            showMessage('Выберите файлы для загрузки', 'error');
            return;
        }

        // Создаем FormData и добавляем файлы
        const formData = new FormData();

        // Добавляем CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        formData.append('csrfmiddlewaretoken', csrfToken);

        // Добавляем файлы
        selectedFilesArray.forEach(file => {
            formData.append('files', file);
        });

        // Блокируем кнопку и показываем загрузку
        submitBtn.disabled = true;
        updateUploadStatus('Загрузка...', true);

        // Отправляем запрос
        fetch(uploadForm.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (response.redirected) {
                // Django сделал redirect - перезагружаем страницу
                window.location.href = response.url;
            } else {
                return response.text();
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки:', error);
            showMessage('Произошла ошибка при загрузке файлов', 'error');
            updateUploadStatus('Загрузить файлы', false);
            submitBtn.disabled = false;
        });
    });

    // Предотвращение drag & drop на всей странице
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, function(e) {
            e.preventDefault();
            e.stopPropagation();
        });
    });
});