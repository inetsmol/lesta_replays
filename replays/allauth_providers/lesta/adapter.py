# replays/allauth_providers/lesta/adapter.py
"""Кастомный адаптер для социальных провайдеров."""

import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

logger = logging.getLogger(__name__)


class LestaSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Кастомный адаптер для всех социальных провайдеров.

    Для Lesta: автоматически связывает аккаунт, если пользователь уже залогинен.
    Для остальных: стандартное поведение django-allauth.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Автоматически связать аккаунт, если пользователь уже залогинен.

        Применяется ТОЛЬКО к Lesta провайдеру.
        Для Google/Yandex используется стандартное поведение.

        Args:
            request: Django request объект
            sociallogin: SocialLogin объект
        """
        # Только для новых социальных логинов
        if sociallogin.is_existing:
            return

        # ТОЛЬКО для Lesta провайдера
        if sociallogin.account.provider != 'lesta':
            # Для Google/Yandex - стандартное поведение
            return super().pre_social_login(request, sociallogin)

        # Если пользователь залогинен - автоматически связываем аккаунт
        if request.user.is_authenticated:
            logger.info(
                f"User {request.user.username} is already logged in. "
                f"Connecting {sociallogin.account.provider} account."
            )
            # Автоматически связываем sociallogin с текущим пользователем
            sociallogin.connect(request, request.user)
            return
