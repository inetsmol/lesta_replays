# Интеграция Lesta OpenID - Завершена ✅

## Что реализовано

Успешно интегрирована аутентификация через Lesta Games OpenID API в проект Django с использованием кастомного провайдера для django-allauth.

### Созданные файлы

#### 1. **Lesta Provider** (`replays/allauth_providers/lesta/`)

**Структура:**
```
replays/allauth_providers/
├── __init__.py
└── lesta/
    ├── __init__.py
    ├── client.py           # HTTP клиент для Lesta API
    ├── provider.py         # LestaProvider и LestaAccount классы
    ├── views.py            # LestaOAuth2Adapter и callback views
    └── urls.py             # URL patterns
```

**Ключевые компоненты:**

- **`client.py`** - `LestaAPIClient` для работы с Lesta API:
  - `get_login_url()` - формирование URL для авторизации
  - `prolongate_token()` - продление срока действия токена
  - `logout()` - инвалидация токена

- **`provider.py`** - `LestaProvider` и `LestaAccount`:
  - Регистрация провайдера в django-allauth
  - Извлечение `account_id` и `nickname` из callback
  - Email НЕ возвращается API (будет запрошен у пользователя)

- **`views.py`** - `LestaOAuth2Adapter`:
  - Обработка нестандартного OAuth2 flow Lesta
  - Парсинг токена и данных из URL параметров
  - Создание `SocialLogin` объекта

- **`urls.py`** - URL routing для провайдера

#### 2. **Middleware** (`replays/middleware.py`)

**`LestaTokenRefreshMiddleware`**:
- Автоматически продлевает Lesta токены за 24 часа до истечения
- Работает для всех аутентифицированных пользователей
- Не ломает запрос при ошибке продления

#### 3. **Signal Handlers** (`replays/signals.py`)

**Реализованные сигналы:**

1. **`sync_lesta_player`** (на `pre_social_login`):
   - Создаёт или обновляет модель `Player` при входе через Lesta
   - Синхронизирует `accountDBID`, `real_name`, `name`

2. **`update_user_nickname`** (на `social_account_updated`):
   - Обновляет `first_name` пользователя актуальным никнеймом

3. **`lesta_logout`** (на `user_logged_out`):
   - Инвалидирует токен на стороне Lesta при выходе
   - Удаляет токен из базы данных

#### 4. **Apps Config** (`replays/apps.py`)

**`ReplaysConfig`**:
- Регистрирует signal handlers при запуске приложения

#### 5. **Frontend** (`templates/account/login.html`)

**Добавлена кнопка "Войти через Lesta ID":**
- Оранжевый дизайн (цвет Lesta Games)
- Иконка танка (SVG)
- Tailwind CSS стили
- Интеграция с django-allauth template tags

### Обновлённые файлы

#### 1. **Settings** (`lesta_replays/settings.py`)

**Изменения:**

```python
# INSTALLED_APPS
"replays.allauth_providers.lesta",  # Добавлен Lesta provider

# MIDDLEWARE
'replays.middleware.LestaTokenRefreshMiddleware',  # Продление токенов

# SOCIALACCOUNT_PROVIDERS
'lesta': {
    'APP': {
        'client_id': os.getenv('LESTA_OAUTH2_APLICATON_ID'),
        'key': os.getenv('LESTA_OAUTH2_APLICATON_ID'),
    },
    'API_BASE_URL': os.getenv('LESTA_API_BASE_URL', 'https://api.tanki.su/wot/auth'),
    'VERIFIED_EMAIL': False,  # Lesta не возвращает email
}

# Переменные окружения
LESTA_APPLICATION_ID = os.getenv("LESTA_OAUTH2_APLICATON_ID", "")
LESTA_API_BASE_URL = os.getenv("LESTA_API_BASE_URL", "https://api.tanki.su/wot/auth")
```

#### 2. **Environment** (`.env.example`)

**Добавлено:**
```bash
LESTA_OAUTH2_APLICATON_ID=111
```

---

## Следующие шаги для запуска

### 1. Создать Social Application в Django Admin

После запуска сервера (`python manage.py runserver`):

1. Перейдите в админку: http://localhost:8000/adminn/
2. Откройте **Sites** → **Social applications** → **Add social application**
3. Заполните форму:
   - **Provider**: Lesta Games
   - **Name**: Lesta Production (или любое имя)
   - **Client ID**: `b351569dc0d5dc0908be75ca50534e3a` (из `.env`)
   - **Secret key**: оставьте пустым (Lesta не использует secret)
   - **Sites**: выберите `example.com` или ваш домен

4. Сохраните

### 2. Зарегистрировать redirect_uri на developers.lesta.ru

⚠️ **ВАЖНО**: Для работы на production необходимо:

1. Зайти на https://developers.lesta.ru/
2. Найти ваше приложение (Application ID: `b351569dc0d5dc0908be75ca50534e3a`)
3. Добавить **Redirect URI**:
   - Development: `http://localhost:8000/accounts/lesta/login/callback/`
   - Production: `https://lesta-replays.ru/accounts/lesta/login/callback/`

### 3. Обновить ALLOWED_HOSTS и CSRF_TRUSTED_ORIGINS

Для production в `settings.py`:

```python
ALLOWED_HOSTS = ["lesta-replays.ru", "localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = [
    "https://lesta-replays.ru",
]
```

### 4. Проверить что HTTPS включен

⚠️ **КРИТИЧНО**: Lesta требует HTTPS для всех запросов с токенами.

В production убедитесь что:
```python
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

---

## Тестирование

### Локальное тестирование (Development)

1. **Запустить сервер:**
   ```bash
   python manage.py runserver
   ```

2. **Перейти на страницу входа:**
   ```
   http://localhost:8000/accounts/login/
   ```

3. **Нажать "Войти через Lesta ID"**

4. **Ожидаемый flow:**
   - Редирект на `api.tanki.su/wot/auth/login/`
   - Ввод логина/пароля Lesta Games
   - Редирект обратно на сайт: `http://localhost:8000/accounts/lesta/login/callback/?status=ok&...`
   - Автоматический вход на сайт
   - Создание User и Player в базе данных

### Проверка в базе данных

После успешного входа проверьте:

```python
python manage.py shell

from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount, SocialToken
from replays.models import Player

# Проверить пользователя
user = User.objects.last()
print(f"Username: {user.username}")
print(f"First name: {user.first_name}")

# Проверить social account
social = SocialAccount.objects.filter(user=user, provider='lesta').first()
print(f"Account ID: {social.uid}")
print(f"Nickname: {social.extra_data.get('nickname')}")

# Проверить токен
token = SocialToken.objects.filter(account=social).first()
print(f"Token: {token.token[:20]}...")
print(f"Expires at: {token.expires_at}")

# Проверить Player
player = Player.objects.filter(accountDBID=social.uid).first()
print(f"Player: {player.real_name} (ID: {player.id})")
```

### Проверка продления токена

Middleware автоматически продлевает токены за 24 часа до истечения.

**Для тестирования:**
1. Измените expires_at токена на "завтра"
2. Перезагрузите любую страницу (будучи авторизованным)
3. Проверьте логи - должна быть запись о продлении

### Проверка logout

1. Нажмите "Выход" на сайте
2. Проверьте что токен удалён из базы
3. Проверьте логи - должна быть запись об инвалидации токена

---

## Известные особенности

### 1. Email не возвращается Lesta API

При первом входе через Lesta пользователю будет показана форма для ввода email.

**Это ожидаемое поведение.** Lesta API возвращает только:
- `account_id` (уникальный ID)
- `nickname` (имя в игре)
- `access_token`
- `expires_at`

### 2. Username = Nickname

Username пользователя будет равен игровому никнейму.

Если никнейм содержит недопустимые символы - Django может выдать ошибку валидации.

**Решение:** Можно изменить `extract_common_fields()` в `provider.py`:
```python
def extract_common_fields(self, data):
    nickname = data.get('nickname', '')
    # Сгенерировать безопасный username
    safe_username = f"lesta_{data['account_id']}"

    return {
        'username': safe_username,  # Безопасный username
        'first_name': nickname,      # Настоящий никнейм
    }
```

### 3. Токен живёт до 2 недель

По умолчанию Lesta токены действуют 2 недели. Middleware продлевает их автоматически.

Если пользователь не заходил на сайт больше 2 недель - потребуется повторная авторизация.

### 4. Logout может занять до 10 минут

Из-за кеширования на стороне Lesta токен может быть валиден до 10 минут после logout.

Это нормальное поведение согласно документации Lesta API.

---

## Troubleshooting

### Ошибка: "LESTA_APPLICATION_ID not configured"

**Причина:** Не установлена переменная окружения.

**Решение:**
```bash
# В .env файле
LESTA_OAUTH2_APLICATON_ID=b351569dc0d5dc0908be75ca50534e3a
```

### Ошибка: "Missing required parameters from Lesta"

**Причина:** Callback от Lesta не содержит обязательных параметров.

**Возможные причины:**
1. Неверный redirect_uri (не зарегистрирован на developers.lesta.ru)
2. Пользователь отменил авторизацию
3. Истекло время ожидания

**Решение:**
- Проверьте логи: должна быть запись с кодом ошибки (401, 403, 410)
- Проверьте redirect_uri в настройках приложения на developers.lesta.ru

### Кнопка "Войти через Lesta ID" не отображается

**Причина:** SocialApp не создано в админке.

**Решение:**
1. Перейдите в админку → Social applications
2. Создайте SocialApp для провайдера "Lesta Games"
3. Обновите страницу входа

### Ошибка при продлении токена

**Симптомы:** В логах ошибки "Failed to refresh Lesta token"

**Причины:**
1. Токен уже истёк (не может быть продлён)
2. Проблемы с сетью
3. Lesta API недоступен

**Решение:**
- Middleware не ломает запрос при ошибке
- Пользователь сможет продолжить работу с сайтом
- При следующем входе потребуется повторная авторизация

---

## Документация

- **План реализации**: [docs/LESTA_OPENID_IMPLEMENTATION_PLAN.md](LESTA_OPENID_IMPLEMENTATION_PLAN.md)
- **Lesta API Docs**: https://developers.lesta.ru/reference/all/wot/auth/login/
- **Django-allauth Docs**: https://django-allauth.readthedocs.io/

---

## Дальнейшее развитие

### Рекомендуемые улучшения:

1. **Unit тесты** - покрыть тестами LestaAPIClient, LestaProvider, views
2. **Integration тесты** - end-to-end тесты авторизации
3. **Отображение игрового профиля** - показывать связанный Player в профиле пользователя
4. **Синхронизация статистики** - периодически обновлять данные игрока из Lesta API
5. **Множественные аккаунты** - поддержка привязки нескольких Lesta аккаунтов к одному User

### Опциональные фичи:

1. **Автоматическое связывание реплеев**:
   - При входе через Lesta автоматически связать все реплеи этого игрока с User
   - Обновить `Replay.user` для реплеев где `owner.accountDBID == social_account.uid`

2. **Badges и достижения**:
   - Отображать значок "Подтверждён через Lesta ID" в профиле
   - Отображать игровой рейтинг и статистику

3. **Social features**:
   - "Мои друзья в игре" - список игроков из clan
   - Возможность найти реплеи своих clanmates

---

## Поддержка

При возникновении проблем:
1. Проверьте логи Django: `tail -f logs/django.log`
2. Проверьте Sentry dashboard (если настроен)
3. Проверьте настройки на developers.lesta.ru

**Статус**: ✅ **Готово к тестированию**

**Дата**: 2025-02-18
