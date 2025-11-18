# План реализации аутентификации через Lesta OpenID

## Обзор

Документ описывает план интеграции аутентификации через Lesta API (OpenID) в существующий Django проект с django-allauth.

**Цель**: Добавить возможность авторизации пользователей через их игровой аккаунт World of Tanks (Lesta Games) наряду с существующими методами (Google, Yandex, email/password).

---

## Текущее состояние

### Установленная система аутентификации

Проект использует **django-allauth** для управления аутентификацией:

- **Базовая аутентификация**: username/email + password
- **OAuth провайдеры**: Google, Yandex
- **Верификация email**: обязательная для локальных аккаунтов
- **Бэкенды**: `ModelBackend` + `AuthenticationBackend` (allauth)

### Конфигурация

**Файл**: [lesta_replays/settings.py:113-141](lesta_replays/settings.py#L113-L141)

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SOCIALACCOUNT_PROVIDERS = {
    'google': {...},
    'yandex': {...}
}
```

**Переменные окружения** (`.env`):
- `GOOGLE_OAUTH2_CLIENT_ID`
- `GOOGLE_OAUTH2_CLIENT_SECRET`
- `YANDEX_OAUTH2_CLIENT_ID`
- `YANDEX_OAUTH2_CLIENT_SECRET`
- `LESTA_OAUTH2_APLICATON_ID`

### URL структура

**Файл**: [lesta_replays/urls.py:56](lesta_replays/urls.py#L56)

```python
path("accounts/", include("allauth.urls")),
```

Доступные endpoints:
- `/accounts/login/` - страница входа
- `/accounts/signup/` - регистрация
- `/accounts/google/login/` - вход через Google
- `/accounts/yandex/login/` - вход через Yandex

---

## Особенности Lesta OpenID API

### Отличия от стандартного OAuth2

Lesta API **НЕ** использует стандартный протокол OAuth2/OpenID Connect. Это **упрощенный кастомный протокол**:

**Стандартный OAuth2 flow:**
```
1. Redirect to provider → 2. User authorizes → 3. Code returned
4. Exchange code for token → 5. Get user info
```

**Lesta OpenID flow:**
```
1. Redirect to Lesta login → 2. User authorizes
3. DIRECT redirect с token и user info в URL параметрах
```

### Спецификация Lesta API

#### 1. Вход (Login)

**Endpoint**: `https://api.tanki.su/wot/auth/login/`

**Обязательные параметры**:
- `application_id` - ID приложения из `.env`
- `redirect_uri` - URL обратного перенаправления (наш callback)

**Опциональные параметры**:
- `expires_at` - срок действия токена (timestamp или дельта в секундах, макс. 2 недели)
- `display` - тип UI: `page` (по умолчанию) или `popup`
- `nofollow=1` - вернуть URL в JSON вместо редиректа

**Успешный ответ** (параметры в `redirect_uri`):
```
?status=ok
&access_token=abc123...
&expires_at=1234567890
&account_id=12345678
&nickname=PlayerName
```

**Ответ при ошибке**:
```
?status=error
&code=ERROR_CODE
&message=Error description
```

**Коды ошибок**:
- `401` `AUTH_CANCEL` - пользователь отменил авторизацию
- `403` `AUTH_EXPIRED` - превышено время ожидания
- `410` `AUTH_ERROR` - общая ошибка аутентификации

#### 2. Продление токена (Prolong)

**Endpoint**: `https://api.tanki.su/wot/auth/prolongate/`

**Параметры**:
- `application_id` - ID приложения
- `access_token` - текущий действующий токен
- `expires_at` - новый срок действия (опционально)

**Ответ**:
```json
{
  "status": "ok",
  "data": {
    "access_token": "new_token_xyz...",
    "account_id": 12345678,
    "expires_at": 1234567890
  }
}
```

#### 3. Выход (Logout)

**Endpoint**: `https://api.tanki.su/wot/auth/logout/`

**Параметры**:
- `application_id` - ID приложения
- `access_token` - токен для инвалидации

**Ответ**: `{"status": "ok"}`

### Безопасность

⚠️ **КРИТИЧНО**:
1. Все запросы с `access_token` должны идти по **HTTPS**
2. Токен действует **до 2 недель** с момента выдачи
3. Токен может быть валиден до **10 минут после logout** (из-за кеша)
4. Пользователь может завершить сессию в Личном кабинете Lesta
5. Функция "выход" **обязательна** для приложений

---

## Архитектура решения

### Вариант 1: Custom Provider для django-allauth ⭐ **РЕКОМЕНДУЕТСЯ**

**Преимущества**:
- ✅ Единая система аутентификации с Google/Yandex
- ✅ Переиспользование всей инфраструктуры allauth (session management, email handling, forms)
- ✅ Стандартные URL patterns (`/accounts/lesta/login/`)
- ✅ Автоматическое связывание аккаунтов (если email совпадает)
- ✅ Единая админка для управления social apps

**Недостатки**:
- ⚠️ Требуется написать кастомный provider (Lesta API не совместим с OAuth2 из коробки)
- ⚠️ Средняя сложность реализации (~200-300 строк кода)

**Структура**:
```
replays/
  allauth_providers/
    lesta/
      __init__.py
      provider.py      # LestaProvider class
      views.py         # LestaOAuth2Adapter, callback view
      urls.py          # URL patterns
      tests.py         # Unit tests
```

### Вариант 2: Полностью кастомная реализация

**Преимущества**:
- ✅ Полный контроль над процессом
- ✅ Минимальные зависимости от allauth

**Недостатки**:
- ❌ Дублирование логики (session, user creation, error handling)
- ❌ Отдельная система URL (`/lesta/login/` вместо `/accounts/lesta/login/`)
- ❌ Сложнее поддерживать консистентность с другими провайдерами
- ❌ Больше кода и тестов

---

## Рекомендуемое решение: Custom Provider

### Этап 1: Подготовка окружения

#### 1.1. Добавить переменные в `.env`

```bash
# Lesta API
LESTA_APPLICATION_ID=b351569dc0d5dc0908be75ca50534e3a
LESTA_API_BASE_URL=https://api.tanki.su/wot/auth
```

#### 1.2. Обновить `settings.py`

**Файл**: [lesta_replays/settings.py:306-326](lesta_replays/settings.py#L306-L326)

```python
# Добавить в INSTALLED_APPS
INSTALLED_APPS = [
    # ...
    "allauth.socialaccount.providers.lesta",  # НОВОЕ
]

# Добавить в SOCIALACCOUNT_PROVIDERS
SOCIALACCOUNT_PROVIDERS = {
    'google': {...},
    'yandex': {...},
    'lesta': {  # НОВОЕ
        'APP': {
            'client_id': os.getenv('LESTA_APPLICATION_ID'),
            'key': os.getenv('LESTA_APPLICATION_ID'),  # для совместимости
        },
        'API_BASE_URL': os.getenv('LESTA_API_BASE_URL', 'https://api.tanki.su/wot/auth'),
        'VERIFIED_EMAIL': False,  # Lesta не возвращает email
    }
}

# Переменная окружения
LESTA_APPLICATION_ID = os.getenv("LESTA_APPLICATION_ID", "")
LESTA_API_BASE_URL = os.getenv("LESTA_API_BASE_URL", "https://api.tanki.su/wot/auth")
```

### Этап 2: Реализация Custom Provider

#### 2.1. Структура файлов

```
replays/
  allauth_providers/
    __init__.py
    lesta/
      __init__.py
      provider.py      # Конфигурация провайдера
      views.py         # OAuth adapter и callback
      urls.py          # URL routing
      client.py        # HTTP клиент для Lesta API
      tests.py         # Тесты
```

#### 2.2. Provider класс (`provider.py`)

**Задачи**:
- Регистрация провайдера в allauth
- Определение имени, ID, URL patterns
- Конфигурация scope (для Lesta - пустой)

```python
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider

class LestaAccount(ProviderAccount):
    """Представление аккаунта Lesta."""

    def get_profile_url(self):
        # URL профиля игрока на сайте Lesta
        return f"https://tanki.su/ru/community/accounts/{self.account.uid}/"

    def get_avatar_url(self):
        # Lesta API не возвращает аватар, можно использовать дефолтный
        return None

    def to_str(self):
        dflt = super(LestaAccount, self).to_str()
        return self.account.extra_data.get('nickname', dflt)


class LestaProvider(OAuth2Provider):
    id = 'lesta'
    name = 'Lesta Games'
    account_class = LestaAccount

    def extract_uid(self, data):
        """Извлечь уникальный ID пользователя."""
        return str(data['account_id'])

    def extract_common_fields(self, data):
        """Извлечь общие поля для User модели."""
        return {
            'username': data.get('nickname', ''),
            'first_name': data.get('nickname', ''),
        }

    def get_default_scope(self):
        """Lesta API не использует scopes."""
        return []


provider_classes = [LestaProvider]
```

#### 2.3. HTTP клиент (`client.py`)

**Задачи**:
- Формирование URL для редиректа на Lesta
- Обработка callback с токеном
- Продление токена
- Logout (инвалидация токена)

```python
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class LestaAPIClient:
    """Клиент для работы с Lesta OpenID API."""

    def __init__(self, application_id=None, base_url=None):
        self.application_id = application_id or settings.LESTA_APPLICATION_ID
        self.base_url = (base_url or settings.LESTA_API_BASE_URL).rstrip('/')

        if not self.application_id:
            raise ImproperlyConfigured("LESTA_APPLICATION_ID not configured")

    def get_login_url(self, redirect_uri, expires_at=None, display='page'):
        """
        Сформировать URL для редиректа пользователя на страницу входа Lesta.

        Args:
            redirect_uri: URL для обратного редиректа после авторизации
            expires_at: Срок действия токена (timestamp или дельта в секундах)
            display: 'page' или 'popup'

        Returns:
            str: URL для редиректа
        """
        params = {
            'application_id': self.application_id,
            'redirect_uri': redirect_uri,
            'display': display,
        }

        if expires_at:
            params['expires_at'] = expires_at

        url = f"{self.base_url}/login/"
        # Формируем query string вручную для контроля
        from urllib.parse import urlencode
        return f"{url}?{urlencode(params)}"

    def prolongate_token(self, access_token, expires_at=None):
        """
        Продлить срок действия access_token.

        Args:
            access_token: Текущий действующий токен
            expires_at: Новый срок действия (опционально)

        Returns:
            dict: {'access_token', 'account_id', 'expires_at'}

        Raises:
            requests.HTTPError: При ошибке API
        """
        params = {
            'application_id': self.application_id,
            'access_token': access_token,
        }

        if expires_at:
            params['expires_at'] = expires_at

        url = f"{self.base_url}/prolongate/"
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get('status') != 'ok':
            raise ValueError(f"Lesta API error: {data}")

        return data['data']

    def logout(self, access_token):
        """
        Инвалидировать access_token.

        Args:
            access_token: Токен для удаления

        Returns:
            bool: True если успешно
        """
        params = {
            'application_id': self.application_id,
            'access_token': access_token,
        }

        url = f"{self.base_url}/logout/"
        response = requests.post(url, data=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get('status') == 'ok'
```

#### 2.4. Views и Adapter (`views.py`)

**Задачи**:
- Обработка callback от Lesta с параметрами в URL
- Парсинг `access_token`, `account_id`, `nickname`, `expires_at`
- Интеграция с allauth flow

```python
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)
from django.urls import reverse

from .client import LestaAPIClient
from .provider import LestaProvider


class LestaOAuth2Adapter(OAuth2Adapter):
    """Adapter для Lesta OpenID (не стандартный OAuth2)."""

    provider_id = LestaProvider.id
    supports_state = False  # Lesta не использует state parameter

    def __init__(self, request):
        super().__init__(request)
        self.client = LestaAPIClient()

    def complete_login(self, request, app, token, **kwargs):
        """
        Завершить процесс логина после получения токена от Lesta.

        Lesta возвращает данные напрямую в callback URL:
        ?status=ok&access_token=...&account_id=...&nickname=...&expires_at=...
        """
        # Парсим параметры из callback URL
        status = request.GET.get('status')

        if status == 'error':
            code = request.GET.get('code')
            message = request.GET.get('message')
            raise ValueError(f"Lesta auth error [{code}]: {message}")

        if status != 'ok':
            raise ValueError(f"Unexpected Lesta response status: {status}")

        # Извлекаем данные пользователя
        data = {
            'account_id': request.GET.get('account_id'),
            'nickname': request.GET.get('nickname'),
            'access_token': request.GET.get('access_token'),
            'expires_at': request.GET.get('expires_at'),
        }

        if not all([data['account_id'], data['nickname'], data['access_token']]):
            raise ValueError("Missing required parameters from Lesta")

        # Создаем SocialLogin объект
        from allauth.socialaccount.models import SocialLogin
        login = self.get_provider().sociallogin_from_response(request, data)

        return login

    def get_callback_url(self, request, app):
        """URL для обратного редиректа от Lesta."""
        callback_url = reverse('lesta_callback')
        return request.build_absolute_uri(callback_url)


# Views
oauth2_login = OAuth2LoginView.adapter_view(LestaOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(LestaOAuth2Adapter)
```

#### 2.5. URL patterns (`urls.py`)

```python
from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns
from .provider import LestaProvider

urlpatterns = default_urlpatterns(LestaProvider)
```

### Этап 3: Интеграция в проект

#### 3.1. Регистрация провайдера

**Файл**: `replays/allauth_providers/lesta/__init__.py`

```python
default_app_config = 'replays.allauth_providers.lesta.provider.LestaProvider'
```

#### 3.2. Обновить `INSTALLED_APPS`

**Файл**: [lesta_replays/settings.py:50-71](lesta_replays/settings.py#L50-L71)

```python
INSTALLED_APPS = [
    # ...
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.yandex",
    "replays.allauth_providers.lesta",  # НОВОЕ
    # ...
]
```

#### 3.3. Добавить в Django Admin

После миграций в админке появится раздел "Social applications". Нужно создать запись:

**Provider**: Lesta Games
**Name**: Lesta Production
**Client ID**: `b351569dc0d5dc0908be75ca50534e3a` (из `.env`)
**Sites**: выбрать текущий сайт

### Этап 4: Frontend интеграция

#### 4.1. Обновить шаблон входа

**Файл**: `templates/account/login.html` (или base template)

Добавить кнопку "Войти через Lesta":

```html
{% load socialaccount %}

<div class="social-login-buttons">
    <!-- Существующие кнопки -->
    <a href="{% provider_login_url 'google' %}" class="btn btn-google">
        <i class="fab fa-google"></i> Войти через Google
    </a>

    <a href="{% provider_login_url 'yandex' %}" class="btn btn-yandex">
        <i class="fab fa-yandex"></i> Войти через Yandex
    </a>

    <!-- НОВАЯ кнопка -->
    <a href="{% provider_login_url 'lesta' %}" class="btn btn-lesta">
        <i class="fas fa-tank"></i> Войти через Lesta ID
    </a>
</div>
```

#### 4.2. CSS стили

```css
.btn-lesta {
    background-color: #ff6600;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 4px;
    font-weight: 600;
    transition: background-color 0.3s;
}

.btn-lesta:hover {
    background-color: #e65c00;
    color: white;
    text-decoration: none;
}
```

### Этап 5: Обработка особых случаев

#### 5.1. Связывание аккаунтов

**Проблема**: Lesta API не возвращает email, только `account_id` и `nickname`.

**Решение 1** - Запрос email после первого входа:
```python
# В provider.py
class LestaProvider(OAuth2Provider):
    def extract_email_addresses(self, data):
        """Lesta не возвращает email - запрашиваем у пользователя."""
        return []  # Пустой список = требуется ввод email
```

Django-allauth автоматически покажет форму для ввода email после первого входа.

**Решение 2** - Использовать `account_id@lesta.placeholder`:
```python
def extract_common_fields(self, data):
    return {
        'username': data.get('nickname', ''),
        'first_name': data.get('nickname', ''),
        'email': f"{data['account_id']}@lesta.placeholder",  # Placeholder
    }
```

⚠️ Рекомендуется **Решение 1** для лучшего UX.

#### 5.2. Обновление никнейма

**Проблема**: Игрок может сменить ник в игре, но в Django он останется старым.

**Решение**: Обновлять `first_name` при каждом входе:

```python
# В views.py
from allauth.socialaccount.signals import social_account_updated

def update_user_nickname(sender, request, sociallogin, **kwargs):
    """Обновить никнейм пользователя при входе через Lesta."""
    if sociallogin.account.provider == 'lesta':
        user = sociallogin.user
        nickname = sociallogin.account.extra_data.get('nickname')
        if nickname and user.first_name != nickname:
            user.first_name = nickname
            user.save(update_fields=['first_name'])

social_account_updated.connect(update_user_nickname)
```

#### 5.3. Продление токена

**Задача**: Обновлять `access_token` перед истечением срока действия.

**Решение**: Middleware или scheduled task (Celery):

```python
# replays/middleware.py
from datetime import datetime, timedelta
from allauth.socialaccount.models import SocialToken
from replays.allauth_providers.lesta.client import LestaAPIClient

class LestaTokenRefreshMiddleware:
    """Обновляет Lesta токены перед истечением."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.client = LestaAPIClient()

    def __call__(self, request):
        if request.user.is_authenticated:
            self._refresh_lesta_token_if_needed(request.user)

        response = self.get_response(request)
        return response

    def _refresh_lesta_token_if_needed(self, user):
        """Обновить токен если до истечения осталось < 24 часа."""
        try:
            token = SocialToken.objects.get(
                account__user=user,
                account__provider='lesta'
            )

            # Проверяем срок действия
            if token.expires_at:
                time_until_expiry = token.expires_at - datetime.now(token.expires_at.tzinfo)

                if time_until_expiry < timedelta(hours=24):
                    # Продлеваем токен
                    new_data = self.client.prolongate_token(
                        access_token=token.token,
                        expires_at=int((datetime.now() + timedelta(days=14)).timestamp())
                    )

                    token.token = new_data['access_token']
                    token.expires_at = datetime.fromtimestamp(new_data['expires_at'])
                    token.save()

        except SocialToken.DoesNotExist:
            pass  # У пользователя нет Lesta токена
```

Добавить в `settings.py`:
```python
MIDDLEWARE = [
    # ...
    'replays.middleware.LestaTokenRefreshMiddleware',  # После AuthenticationMiddleware
]
```

#### 5.4. Logout

**Задача**: Инвалидировать токен на стороне Lesta при выходе.

**Решение**: Signal handler:

```python
# replays/signals.py
from allauth.account.signals import user_logged_out
from allauth.socialaccount.models import SocialToken
from replays.allauth_providers.lesta.client import LestaAPIClient
import logging

logger = logging.getLogger(__name__)

def lesta_logout(sender, request, user, **kwargs):
    """Инвалидировать Lesta токен при выходе."""
    try:
        token = SocialToken.objects.get(
            account__user=user,
            account__provider='lesta'
        )

        client = LestaAPIClient()
        client.logout(token.token)

        logger.info(f"Lesta token invalidated for user {user.id}")

    except SocialToken.DoesNotExist:
        pass  # У пользователя нет Lesta аккаунта

user_logged_out.connect(lesta_logout)
```

Зарегистрировать в `replays/apps.py`:
```python
class ReplaysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'replays'

    def ready(self):
        import replays.signals  # Импортировать signals
```

### Этап 6: Связь с моделью Player

**Контекст**: В проекте есть модель `Player` с полями `accountDBID`, `real_name`, `fake_name`.

**Цель**: Автоматически связывать Django User с игровым Player при входе через Lesta.

#### 6.1. Расширение модели User

**Вариант 1** - Добавить поле в профиль:

```python
# replays/models.py
from django.contrib.auth.models import User

class UserProfile(models.Model):
    """Расширенный профиль пользователя."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    player = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user.username}"
```

**Вариант 2** - Использовать SocialAccount.extra_data:

```python
# Не требует изменения моделей
# account_id уже хранится в SocialAccount.uid
# Можно получить так:
def get_player_for_user(user):
    from allauth.socialaccount.models import SocialAccount

    try:
        social = SocialAccount.objects.get(user=user, provider='lesta')
        account_id = social.uid  # Это accountDBID
        return Player.objects.get(accountDBID=account_id)
    except (SocialAccount.DoesNotExist, Player.DoesNotExist):
        return None
```

#### 6.2. Автоматическое создание/обновление Player

**Signal handler**:

```python
# replays/signals.py
from allauth.socialaccount.signals import pre_social_login
from replays.models import Player

def sync_lesta_player(sender, request, sociallogin, **kwargs):
    """Создать/обновить Player при входе через Lesta."""
    if sociallogin.account.provider != 'lesta':
        return

    account_id = sociallogin.account.uid
    nickname = sociallogin.account.extra_data.get('nickname')

    # Создаём или обновляем Player
    player, created = Player.objects.update_or_create(
        accountDBID=account_id,
        defaults={
            'real_name': nickname,
            'name': nickname,  # Если name это login
        }
    )

    if created:
        logger.info(f"Created Player {player.id} for Lesta account {account_id}")
    else:
        logger.info(f"Updated Player {player.id} nickname to {nickname}")

pre_social_login.connect(sync_lesta_player)
```

#### 6.3. Отображение связанного игрока

**В шаблоне профиля**:

```html
{% load socialaccount %}

{% if user.is_authenticated %}
    {% get_social_accounts user as accounts %}

    {% for account in accounts %}
        {% if account.provider == 'lesta' %}
            <div class="lesta-account">
                <h3>Игровой аккаунт</h3>
                <p>
                    <strong>Никнейм:</strong> {{ account.extra_data.nickname }}
                    <br>
                    <strong>ID:</strong> {{ account.uid }}
                    <br>
                    <a href="{{ account.get_profile_url }}" target="_blank">
                        Профиль на tanki.su
                    </a>
                </p>
            </div>
        {% endif %}
    {% endfor %}
{% endif %}
```

### Этап 7: Тестирование

#### 7.1. Unit тесты

**Файл**: `replays/allauth_providers/lesta/tests.py`

```python
from django.test import TestCase, RequestFactory
from unittest.mock import Mock, patch
from .client import LestaAPIClient
from .views import LestaOAuth2Adapter

class LestaAPIClientTest(TestCase):
    def setUp(self):
        self.client = LestaAPIClient(
            application_id='test_app_id',
            base_url='https://api.tanki.su/wot/auth'
        )

    def test_get_login_url(self):
        """Тест формирования URL для логина."""
        url = self.client.get_login_url(
            redirect_uri='https://example.com/callback',
            display='page'
        )

        self.assertIn('application_id=test_app_id', url)
        self.assertIn('redirect_uri=https', url)
        self.assertIn('/login/', url)

    @patch('requests.get')
    def test_prolongate_token(self, mock_get):
        """Тест продления токена."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': 'ok',
            'data': {
                'access_token': 'new_token',
                'account_id': 12345,
                'expires_at': 1234567890
            }
        }
        mock_get.return_value = mock_response

        result = self.client.prolongate_token('old_token')

        self.assertEqual(result['access_token'], 'new_token')
        self.assertEqual(result['account_id'], 12345)

class LestaOAuth2AdapterTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_complete_login_success(self):
        """Тест успешного завершения логина."""
        request = self.factory.get('/callback/', {
            'status': 'ok',
            'access_token': 'abc123',
            'account_id': '12345',
            'nickname': 'TestPlayer',
            'expires_at': '1234567890'
        })

        adapter = LestaOAuth2Adapter(request)
        # ... тест complete_login

    def test_complete_login_error(self):
        """Тест обработки ошибки от Lesta."""
        request = self.factory.get('/callback/', {
            'status': 'error',
            'code': '401',
            'message': 'AUTH_CANCEL'
        })

        adapter = LestaOAuth2Adapter(request)

        with self.assertRaises(ValueError):
            adapter.complete_login(request, None, None)
```

#### 7.2. Integration тесты

```python
from django.test import TestCase, Client
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.contrib.sites.models import Site

class LestaLoginIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()

        # Создать SocialApp для тестов
        site = Site.objects.get_current()
        app = SocialApp.objects.create(
            provider='lesta',
            name='Lesta Test',
            client_id='test_app_id',
        )
        app.sites.add(site)

    def test_login_redirects_to_lesta(self):
        """Тест редиректа на Lesta при клике на кнопку входа."""
        response = self.client.get('/accounts/lesta/login/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('api.tanki.su', response.url)

    def test_callback_creates_user(self):
        """Тест создания пользователя при callback от Lesta."""
        # Симулируем callback
        response = self.client.get('/accounts/lesta/login/callback/', {
            'status': 'ok',
            'access_token': 'test_token',
            'account_id': '999888',
            'nickname': 'NewPlayer',
            'expires_at': '9999999999'
        })

        # Проверяем что пользователь создан
        user = User.objects.get(username='NewPlayer')
        self.assertIsNotNone(user)

        # Проверяем что SocialAccount создан
        social = SocialAccount.objects.get(user=user, provider='lesta')
        self.assertEqual(social.uid, '999888')
```

#### 7.3. Ручное тестирование

**Checklist**:

1. ✅ Кнопка "Войти через Lesta" отображается на странице входа
2. ✅ Клик по кнопке редиректит на `api.tanki.su/wot/auth/login/`
3. ✅ После ввода учетных данных Lesta редиректит обратно на сайт
4. ✅ Пользователь автоматически авторизован
5. ✅ В профиле отображается связанный игровой аккаунт
6. ✅ При повторном входе не создается дубликат пользователя
7. ✅ Токен продлевается перед истечением (проверить через 13 дней)
8. ✅ При выходе токен инвалидируется на стороне Lesta
9. ✅ Player создается/обновляется автоматически
10. ✅ Email запрашивается при первом входе (если Решение 1)

---

## Миграция и развертывание

### Checklist перед деплоем

1. ✅ Добавить `LESTA_APPLICATION_ID` в production `.env`
2. ✅ Создать SocialApp в Django Admin:
   - Provider: Lesta Games
   - Client ID: значение из `.env`
   - Sites: добавить production сайт
3. ✅ Обновить `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`
4. ✅ Проверить что используется HTTPS (обязательно!)
5. ✅ Запустить тесты: `python manage.py test replays.allauth_providers.lesta`
6. ✅ Создать миграции: `python manage.py makemigrations`
7. ✅ Применить миграции: `python manage.py migrate`
8. ✅ Собрать статику: `python manage.py collectstatic`

### Rollback план

Если что-то пойдет не так:

1. Удалить `"replays.allauth_providers.lesta"` из `INSTALLED_APPS`
2. Откатить миграции: `python manage.py migrate replays <previous_migration>`
3. Удалить SocialApp из админки
4. Перезапустить сервер

---

## Безопасность

### HTTPS обязателен

⚠️ **КРИТИЧНО**: Все запросы с `access_token` должны идти по HTTPS.

**Проверка**:
```python
# settings.py
if not DEBUG:
    assert SECURE_SSL_REDIRECT, "SSL redirect must be enabled in production"
```

### Проверка redirect_uri

Lesta API проверяет что `redirect_uri` соответствует зарегистрированному домену приложения.

**Для разработки**: зарегистрировать `localhost` или `127.0.0.1` в настройках приложения на developers.lesta.ru

**Для production**: использовать только `https://lesta-replays.ru`

### Rate limiting

Рекомендуется добавить rate limiting для endpoint'ов авторизации:

```python
# settings.py
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",
    "signup": "10/h",
    "lesta_login": "10/h",  # НОВОЕ
}
```

### Хранение токенов

- ✅ Токены хранятся в базе данных (таблица `socialaccount_socialtoken`)
- ✅ Используется шифрование на уровне базы (если настроено)
- ❌ НЕ логировать токены в plain text
- ❌ НЕ передавать токены в GET параметрах (кроме официального callback от Lesta)

---

## Мониторинг и логирование

### Логи

Добавить логирование ключевых событий:

```python
# replays/allauth_providers/lesta/views.py
import logging

logger = logging.getLogger(__name__)

class LestaOAuth2Adapter(OAuth2Adapter):
    def complete_login(self, request, app, token, **kwargs):
        status = request.GET.get('status')

        if status == 'error':
            code = request.GET.get('code')
            message = request.GET.get('message')
            logger.error(f"Lesta auth failed: [{code}] {message}", extra={
                'user_ip': request.META.get('REMOTE_ADDR'),
                'code': code,
            })
            raise ValueError(f"Lesta auth error [{code}]: {message}")

        account_id = request.GET.get('account_id')
        logger.info(f"Lesta auth successful for account {account_id}")

        # ...
```

### Sentry

Отфильтровать ожидаемые ошибки:

```python
# settings.py
def _before_send(event, hint):
    # ... существующие фильтры

    # Фильтр для AUTH_CANCEL (пользователь нажал "Отмена")
    exc_type = None
    exc = hint.get("exc_info")
    if exc and exc[0]:
        exc_type = f"{exc[0].__module__}.{exc[0].__name__}"

    if exc_type == "ValueError":
        exc_value = str(exc[1]) if exc and exc[1] else ""
        if "AUTH_CANCEL" in exc_value:
            return None  # Не отправлять в Sentry

    return event
```

### Метрики

Полезные метрики для отслеживания:

- Количество успешных входов через Lesta (по дням)
- Количество ошибок AUTH_CANCEL / AUTH_ERROR
- Время жизни токенов (сколько пользователей активны > 7 дней)
- Количество автоматических продлений токенов

---

## Альтернативные подходы

### Вариант: Использовать django-rest-framework для API

Если в будущем потребуется API для мобильного приложения:

```python
# replays/api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from replays.allauth_providers.lesta.client import LestaAPIClient

class LestaAuthAPIView(APIView):
    """API endpoint для получения Lesta login URL."""

    def get(self, request):
        client = LestaAPIClient()
        redirect_uri = request.build_absolute_uri('/api/auth/lesta/callback/')

        login_url = client.get_login_url(redirect_uri)

        return Response({
            'login_url': login_url
        })
```

---

## FAQ

### Q: Почему не использовать готовый allauth provider?

**A**: Django-allauth не имеет встроенного провайдера для Lesta API. Lesta использует упрощенный кастомный протокол, несовместимый с стандартным OAuth2.

### Q: Нужно ли хранить refresh_token?

**A**: Lesta API не использует refresh tokens. Вместо этого есть метод `/auth/prolongate/` для продления текущего `access_token`.

### Q: Как обрабатывать случай когда пользователь уже зарегистрирован через email?

**A**: Django-allauth автоматически предложит связать аккаунты если email совпадает (если email запрашивается при первом входе через Lesta).

### Q: Можно ли получить email пользователя из Lesta API?

**A**: Нет, Lesta OpenID API возвращает только `account_id` и `nickname`. Email нужно запрашивать у пользователя отдельно.

### Q: Что если токен истек а пользователь офлайн?

**A**: Токен продлевается только когда пользователь заходит на сайт (через middleware). Если токен истек - при следующем входе потребуется повторная авторизация через Lesta.

### Q: Безопасно ли хранить access_token в базе?

**A**: Да, при условии что:
1. База данных защищена
2. Используется HTTPS для всех запросов
3. Доступ к базе имеют только авторизованные сервисы
4. Применяется шифрование на уровне базы (опционально)

---

## Roadmap

### Фаза 1: MVP (1-2 недели)
- [x] Создать структуру провайдера
- [x] Реализовать LestaAPIClient
- [x] Реализовать LestaOAuth2Adapter
- [x] Добавить кнопку "Войти через Lesta"
- [x] Написать базовые unit тесты
- [x] Развернуть на dev окружении

### Фаза 2: Integration (1 неделя)
- [ ] Связывание с моделью Player
- [ ] Обновление никнейма при входе
- [ ] Продление токена через middleware
- [ ] Logout handler
- [ ] Integration тесты

### Фаза 3: Production (1 неделя)
- [ ] Зарегистрировать redirect_uri на developers.lesta.ru
- [ ] Настроить production environment
- [ ] Добавить мониторинг и метрики
- [ ] Провести нагрузочное тестирование
- [ ] Написать документацию для пользователей
- [ ] Deploy на production

### Фаза 4: Improvements (опционально)
- [ ] Автоматическая синхронизация статистики игрока
- [ ] Отображение достижений из Lesta API
- [ ] REST API для мобильных приложений
- [ ] Поддержка других игр Lesta (World of Warships, etc.)

---

## Полезные ссылки

- **Lesta API Docs**: https://developers.lesta.ru/reference/all/wot/auth/login/
- **Django-allauth Docs**: https://django-allauth.readthedocs.io/
- **Django-allauth Custom Providers**: https://django-allauth.readthedocs.io/en/latest/advanced.html#custom-providers
- **Проект CLAUDE.md**: [CLAUDE.md:329-341](CLAUDE.md#L329-L341)

---

## Контакты и поддержка

При возникновении проблем:
1. Проверить логи: `docker-compose logs -f` или `tail -f logs/django.log`
2. Проверить Sentry dashboard
3. Создать issue в репозитории проекта

---

**Документ подготовлен**: 2025-02-18
**Автор**: Claude (Anthropic)
**Версия**: 1.0
