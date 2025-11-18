# replays/allauth_providers/lesta/client.py
"""HTTP клиент для работы с Lesta OpenID API."""

import logging
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class LestaAPIClient:
    """Клиент для работы с Lesta OpenID API."""

    def __init__(self, application_id=None, base_url=None):
        """
        Инициализация клиента.

        Args:
            application_id: ID приложения (из settings или параметр)
            base_url: Базовый URL API (из settings или параметр)
        """
        self.application_id = application_id or getattr(settings, 'LESTA_APPLICATION_ID', None)
        self.base_url = (base_url or getattr(settings, 'LESTA_API_BASE_URL',
                         'https://api.tanki.su/wot/auth')).rstrip('/')

        if not self.application_id:
            raise ImproperlyConfigured(
                "LESTA_APPLICATION_ID not configured in settings. "
                "Please set LESTA_OAUTH2_APLICATON_ID in your .env file."
            )

    def get_login_url(self, redirect_uri, expires_at=None, display='page'):
        """
        Сформировать URL для редиректа пользователя на страницу входа Lesta.

        Args:
            redirect_uri: URL для обратного редиректа после авторизации
            expires_at: Срок действия токена (timestamp или дельта в секундах)
            display: 'page' (по умолчанию) или 'popup'

        Returns:
            str: URL для редиректа на страницу авторизации Lesta
        """
        params = {
            'application_id': self.application_id,
            'redirect_uri': redirect_uri,
            'display': display,
        }

        if expires_at:
            params['expires_at'] = expires_at

        url = f"{self.base_url}/login/"
        full_url = f"{url}?{urlencode(params)}"

        logger.debug(f"Generated Lesta login URL: {full_url}")
        return full_url

    def prolongate_token(self, access_token, expires_at=None):
        """
        Продлить срок действия access_token.

        Args:
            access_token: Текущий действующий токен
            expires_at: Новый срок действия (опционально)

        Returns:
            dict: {'access_token', 'account_id', 'expires_at'}

        Raises:
            requests.HTTPError: При ошибке HTTP
            ValueError: При ошибке API (status != 'ok')
        """
        params = {
            'application_id': self.application_id,
            'access_token': access_token,
        }

        if expires_at:
            params['expires_at'] = expires_at

        url = f"{self.base_url}/prolongate/"

        logger.debug(f"Prolongating Lesta token via {url}")

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'ok':
                error_msg = f"Lesta API error: {data}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info(f"Successfully prolongated token for account {data['data']['account_id']}")
            return data['data']

        except requests.RequestException as e:
            logger.error(f"Failed to prolongate Lesta token: {e}")
            raise

    def logout(self, access_token):
        """
        Инвалидировать access_token на стороне Lesta.

        Args:
            access_token: Токен для удаления

        Returns:
            bool: True если успешно

        Raises:
            requests.HTTPError: При ошибке HTTP
        """
        params = {
            'application_id': self.application_id,
            'access_token': access_token,
        }

        url = f"{self.base_url}/logout/"

        logger.debug(f"Logging out Lesta token via {url}")

        try:
            response = requests.post(url, data=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            success = data.get('status') == 'ok'

            if success:
                logger.info("Successfully invalidated Lesta token")
            else:
                logger.warning(f"Unexpected logout response: {data}")

            return success

        except requests.RequestException as e:
            logger.error(f"Failed to logout from Lesta: {e}")
            raise
