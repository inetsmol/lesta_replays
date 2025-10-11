# Настройка OAuth для входа через Google и Yandex

## Что уже сделано

✅ Установлены необходимые пакеты django-allauth с поддержкой социальных провайдеров  
✅ Обновлены настройки Django для поддержки Google и Yandex  
✅ Обновлены шаблоны входа и регистрации с кнопками социальных сетей  
✅ Выполнены миграции для создания таблиц социальных аккаунтов  
✅ Создан суперпользователь для доступа к админке  
✅ Исправлены ошибки с отсутствующими сайтами и картами  
✅ Настроен сайт в Django для корректной работы allauth  

## Что нужно сделать

### 1. Создать OAuth приложение в Google

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Включите Google+ API:
   - Перейдите в "APIs & Services" → "Library"
   - Найдите "Google+ API" и включите его
4. Создайте OAuth 2.0 credentials:
   - Перейдите в "APIs & Services" → "Credentials"
   - Нажмите "Create Credentials" → "OAuth 2.0 Client IDs"
   - Выберите "Web application"
   - Добавьте авторизованные URI перенаправления:
     - `http://localhost:8000/accounts/google/login/callback/` (для разработки)
     - `https://lesta-replays.ru/accounts/google/login/callback/` (для продакшена)
5. Скопируйте Client ID и Client Secret

### 2. Создать OAuth приложение в Yandex

1. Перейдите в [Yandex OAuth](https://oauth.yandex.ru/)
2. Нажмите "Создать приложение"
3. Заполните форму:
   - Название: "Lesta Replays"
   - Описание: "Сайт для анализа реплеев World of Tanks"
   - Платформы: выберите "Веб-сервисы"
   - Callback URI: 
     - `http://localhost:8000/accounts/yandex/login/callback/` (для разработки)
     - `https://lesta-replays.ru/accounts/yandex/login/callback/` (для продакшена)
4. Скопируйте ID приложения и пароль

### 3. Настроить переменные окружения

Добавьте в файл `.env` следующие переменные:

```env
# OAuth настройки для социальных провайдеров
GOOGLE_OAUTH2_CLIENT_ID=ваш_google_client_id
GOOGLE_OAUTH2_CLIENT_SECRET=ваш_google_client_secret
YANDEX_OAUTH2_CLIENT_ID=ваш_yandex_client_id
YANDEX_OAUTH2_CLIENT_SECRET=ваш_yandex_client_secret
```

### 4. Настроить социальные приложения в Django админке

1. Запустите сервер: `python manage.py runserver`
2. Перейдите в админку: `http://localhost:8000/adminn/`
3. Войдите как суперпользователь (admin/admin123)
4. Перейдите в "Social Applications" → "Social applications"
5. Создайте два приложения:

**Для Google:**
- Provider: Google
- Name: Google OAuth
- Client id: ваш Google Client ID
- Secret key: ваш Google Client Secret
- Sites: выберите ваш сайт

**Для Yandex:**
- Provider: Yandex
- Name: Yandex OAuth
- Client id: ваш Yandex Client ID
- Secret key: ваш Yandex Client Secret
- Sites: выберите ваш сайт

### 5. Проверить работу

1. Перейдите на страницу входа: `http://localhost:8000/accounts/login/`
2. Вы должны увидеть кнопки "Войти через Google" и "Войти через Яндекс"
3. Нажмите на любую из кнопок для проверки

## Возможные проблемы

### Ошибка "SocialApp matching query does not exist"
- Убедитесь, что вы создали социальные приложения в админке Django
- Проверьте, что выбрали правильный сайт

### Ошибка "Invalid redirect_uri"
- Проверьте, что URI перенаправления в OAuth приложениях точно соответствуют указанным выше
- Убедитесь, что нет лишних пробелов или символов

### Кнопки не отображаются
- Убедитесь, что социальные приложения созданы и активны в админке
- Проверьте, что переменные окружения правильно настроены

## Дополнительные настройки

### Настройка домена для продакшена

В файле `settings.py` уже настроены домены для продакшена:
- `lesta-replays.ru` добавлен в `ALLOWED_HOSTS`
- `https://lesta-replays.ru` добавлен в `CSRF_TRUSTED_ORIGINS`

### Безопасность

- Никогда не коммитьте файл `.env` в репозиторий
- Используйте разные OAuth приложения для разработки и продакшена
- Регулярно обновляйте секретные ключи
