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

    def complete_login(self, request, app, token, **kwargs):
        """
        Завершить процесс логина после получения данных от Lesta.

        Lesta возвращает данные напрямую в callback URL:
        ?status=ok&access_token=...&account_id=...&nickname=...&expires_at=...

        Args:
            request: Django request объект
            app: SocialApp instance
            token: Не используется (Lesta возвращает токен в URL)
            **kwargs: Дополнительные параметры

        Returns:
            SocialLogin: Объект для завершения авторизации

        Raises:
            ValueError: При ошибке от Lesta или некорректных данных
        """
        # Парсим параметры из callback URL
        status = request.GET.get('status')

        # Обработка ошибки от Lesta
        if status == 'error':
            code = request.GET.get('code')
            message = request.GET.get('message')
            logger.error(
                f"Lesta auth failed: [{code}] {message}",
                extra={
                    'user_ip': request.META.get('REMOTE_ADDR'),
                    'code': code,
                }
            )
            raise ValueError(f"Lesta auth error [{code}]: {message}")

        # Проверка успешного статуса
        if status != 'ok':
            logger.error(f"Unexpected Lesta response status: {status}")
            raise ValueError(f"Unexpected Lesta response status: {status}")

        # Извлекаем данные пользователя
        account_id = request.GET.get('account_id')
        nickname = request.GET.get('nickname')
        access_token = request.GET.get('access_token')
        expires_at = request.GET.get('expires_at')

        # Валидация обязательных полей
        if not all([account_id, nickname, access_token]):
            logger.error("Missing required parameters from Lesta callback")
            raise ValueError("Missing required parameters from Lesta (account_id, nickname, or access_token)")

        # Формируем данные для создания SocialLogin
        data = {
            'account_id': account_id,
            'nickname': nickname,
            'access_token': access_token,
            'expires_at': expires_at,
        }

        logger.info(f"Lesta auth successful for account {account_id} (nickname: {nickname})")

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


# View instances
oauth2_login = OAuth2LoginView.adapter_view(LestaOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(LestaOAuth2Adapter)
