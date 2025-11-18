# replays/allauth_providers/lesta/views.py
"""Views и adapter для Lesta Games OAuth2."""

import logging
from datetime import datetime, timedelta

from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)
from django.urls import reverse

from .client import LestaAPIClient
from .provider import LestaProvider

logger = logging.getLogger(__name__)


class LestaOAuth2Adapter(OAuth2Adapter):
    """
    Adapter для Lesta OpenID (не стандартный OAuth2).

    Lesta API возвращает токен и данные пользователя сразу в callback URL,
    минуя стандартный OAuth2 flow с обменом кода на токен.
    """

    provider_id = LestaProvider.id
    supports_state = False  # Lesta не использует state parameter

    # URL endpoints (не используются напрямую, т.к. не стандартный OAuth2)
    access_token_url = None
    authorize_url = None
    profile_url = None

    def __init__(self, request):
        super().__init__(request)
        self.client = LestaAPIClient()

    def get_authorize_url(self, request, app):
        """
        Получить URL для авторизации пользователя.

        Args:
            request: Django request объект
            app: SocialApp instance

        Returns:
            str: URL для редиректа на страницу авторизации Lesta
        """
        callback_url = self.get_callback_url(request, app)
        return self.client.get_login_url(redirect_uri=callback_url)

    def complete_login(self, request, app, token, **kwargs):
        """
        Завершить процесс логина после получения данных от Lesta.

        Args:
            request: Django request объект
            app: SocialApp instance
            token: Токен (уже распарсенный через parse_token)
            **kwargs: Дополнительные параметры

        Returns:
            SocialLogin: Объект для завершения авторизации
        """
        # Извлекаем данные из request.GET (они уже провалидированы в LestaCallbackView)
        account_id = request.GET.get('account_id')
        nickname = request.GET.get('nickname')

        # Формируем данные для provider
        data = {
            'account_id': account_id,
            'nickname': nickname,
        }

        # Создаем SocialLogin через provider
        return self.get_provider().sociallogin_from_response(request, data)

    def get_callback_url(self, request, app):
        """
        Получить URL для callback от Lesta.

        Args:
            request: Django request объект
            app: SocialApp instance

        Returns:
            str: Абсолютный URL для callback
        """
        callback_path = reverse('lesta_callback')
        callback_url = request.build_absolute_uri(callback_path)

        logger.debug(f"Lesta callback URL: {callback_url}")
        return callback_url

    def parse_token(self, data):
        """
        Парсинг токена из данных Lesta.

        Переопределяем метод, т.к. Lesta возвращает токен в URL params,
        а не в стандартном OAuth2 формате.

        Args:
            data: Словарь с данными от Lesta

        Returns:
            dict: Структура токена для allauth
        """
        expires_at_timestamp = data.get('expires_at')

        # Преобразуем timestamp в datetime если есть
        if expires_at_timestamp:
            try:
                expires_at = datetime.fromtimestamp(int(expires_at_timestamp))
            except (ValueError, TypeError):
                # Если не удалось распарсить - ставим 2 недели от текущего момента
                expires_at = datetime.now() + timedelta(days=14)
        else:
            # По умолчанию - 2 недели
            expires_at = datetime.now() + timedelta(days=14)

        return {
            'access_token': data.get('access_token'),
            'token_type': 'bearer',  # Lesta использует bearer tokens
            'expires_at': expires_at.timestamp() if expires_at else None,
        }


class LestaCallbackView(OAuth2CallbackView):
    """
    Кастомный callback view для обработки нестандартного Lesta OAuth2 flow.

    Lesta возвращает данные напрямую в URL параметрах, минуя обмен code на token.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Обработать callback от Lesta.

        Args:
            request: Django request объект
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы

        Returns:
            HttpResponse: Результат обработки авторизации
        """
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        # Парсим параметры от Lesta
        status = request.GET.get('status')

        # Проверка ошибки
        if status == 'error':
            code = request.GET.get('code')
            message = request.GET.get('message')
            logger.error(f"Lesta auth error: [{code}] {message}")
            # Редирект на страницу ошибки входа
            return HttpResponseRedirect(reverse('socialaccount_login_error'))

        # Проверка успешного статуса
        if status != 'ok':
            logger.error(f"Unexpected Lesta status: {status}")
            return HttpResponseRedirect(reverse('socialaccount_login_error'))

        # Извлекаем данные
        account_id = request.GET.get('account_id')
        nickname = request.GET.get('nickname')
        access_token = request.GET.get('access_token')
        expires_at = request.GET.get('expires_at')

        # Валидация
        if not all([account_id, nickname, access_token]):
            logger.error("Missing required Lesta parameters")
            return HttpResponseRedirect(reverse('socialaccount_login_error'))

        logger.info(f"Lesta callback: account_id={account_id}, nickname={nickname}")

        # Создаём токен для allauth
        token_data = self.adapter.parse_token({
            'access_token': access_token,
            'expires_at': expires_at,
        })

        # Завершаем процесс логина (app не используется в Lesta)
        try:
            from allauth.socialaccount.helpers import complete_social_login
            from allauth.socialaccount.models import SocialToken
            from datetime import datetime

            # Создаём SocialLogin через adapter
            login = self.adapter.complete_login(request, app=None, token=token_data)

            # Создаём SocialToken объект (а не dict)
            expires_at_dt = None
            if token_data.get('expires_at'):
                expires_at_dt = datetime.fromtimestamp(token_data['expires_at'])

            social_token = SocialToken(
                token=access_token,
                token_secret='',  # Lesta не использует token_secret
                expires_at=expires_at_dt
            )
            login.token = social_token

            # Завершаем социальный вход через helper из allauth
            return complete_social_login(request, login)
        except Exception as e:
            logger.exception(f"Failed to complete Lesta login: {e}")
            return HttpResponseRedirect(reverse('socialaccount_login_error'))


# View instances
oauth2_login = OAuth2LoginView.adapter_view(LestaOAuth2Adapter)
oauth2_callback = LestaCallbackView.adapter_view(LestaOAuth2Adapter)
