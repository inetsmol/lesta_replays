# replays/allauth_providers/lesta/adapter.py
"""Кастомный адаптер для социальных провайдеров."""

import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()


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

    def populate_user(self, request, sociallogin, data):
        """
        Заполняет данные пользователя из данных социального провайдера.

        Исправляет username: использует часть до @ вместо полного email.
        """
        user = super().populate_user(request, sociallogin, data)

        # Если username совпадает с email или содержит @, берем только часть до @
        if user.username and '@' in user.username:
            base_username = user.username.split('@')[0]

            # Проверяем уникальность
            if User.objects.filter(username=base_username).exists():
                # Генерируем уникальный username
                counter = 1
                new_username = f"{base_username}{counter}"
                while User.objects.filter(username=new_username).exists():
                    counter += 1
                    new_username = f"{base_username}{counter}"
                user.username = new_username
                logger.info(
                    f"Username '{base_username}' already exists. "
                    f"Using '{new_username}' instead."
                )
            else:
                user.username = base_username
                logger.info(
                    f"Generated username '{base_username}' from email '{user.email}'"
                )

        return user
