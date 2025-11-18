# replays/middleware.py
"""Middleware для работы с Lesta токенами."""

import logging
from datetime import datetime, timedelta, timezone

from allauth.socialaccount.models import SocialToken
from replays.allauth_providers.lesta.client import LestaAPIClient

logger = logging.getLogger(__name__)


class LestaTokenRefreshMiddleware:
    """
    Middleware для автоматического продления Lesta токенов.

    Проверяет токены аутентифицированных пользователей и продлевает
    их если до истечения срока действия осталось менее 24 часов.
    """

    def __init__(self, get_response):
        """
        Инициализация middleware.

        Args:
            get_response: Следующий middleware или view в цепочке
        """
        self.get_response = get_response
        try:
            self.client = LestaAPIClient()
        except Exception as e:
            logger.warning(f"Failed to initialize LestaAPIClient in middleware: {e}")
            self.client = None

    def __call__(self, request):
        """
        Обработка запроса.

        Args:
            request: Django request объект

        Returns:
            Response объект
        """
        if request.user.is_authenticated and self.client:
            self._refresh_lesta_token_if_needed(request.user)

        response = self.get_response(request)
        return response

    def _refresh_lesta_token_if_needed(self, user):
        """
        Обновить токен если до истечения осталось < 24 часа.

        Args:
            user: Django User instance
        """
        try:
            # Получаем Lesta токен пользователя
            token = SocialToken.objects.filter(
                account__user=user,
                account__provider='lesta'
            ).first()

            if not token:
                return  # У пользователя нет Lesta токена

            # Проверяем срок действия
            if not token.expires_at:
                logger.debug(f"Lesta token for user {user.id} has no expiry date")
                return

            # Убедимся что expires_at timezone-aware
            now = datetime.now(timezone.utc)
            expires_at = token.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            time_until_expiry = expires_at - now

            # Продлеваем если осталось менее 24 часов
            if time_until_expiry < timedelta(hours=24):
                logger.info(
                    f"Prolongating Lesta token for user {user.id} "
                    f"(expires in {time_until_expiry})"
                )

                # Новый срок действия - 2 недели от текущего момента
                new_expires_at = int((now + timedelta(days=14)).timestamp())

                # Продлеваем токен
                new_data = self.client.prolongate_token(
                    access_token=token.token,
                    expires_at=new_expires_at
                )

                # Обновляем токен в базе
                token.token = new_data['access_token']
                token.expires_at = datetime.fromtimestamp(
                    new_data['expires_at'],
                    tz=timezone.utc
                )
                token.save(update_fields=['token', 'expires_at'])

                logger.info(f"Successfully prolongated Lesta token for user {user.id}")

        except SocialToken.DoesNotExist:
            pass  # У пользователя нет Lesta токена
        except Exception as e:
            # Не ломаем запрос если не удалось продлить токен
            logger.error(
                f"Failed to refresh Lesta token for user {user.id}: {e}",
                exc_info=True
            )
