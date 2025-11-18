# replays/signals.py
"""Signal handlers для интеграции Lesta аутентификации."""

import logging

from allauth.account.signals import user_logged_out
from allauth.socialaccount.signals import pre_social_login, social_account_updated
from allauth.socialaccount.models import SocialToken
from django.dispatch import receiver

from replays.allauth_providers.lesta.client import LestaAPIClient
from replays.models import Player

logger = logging.getLogger(__name__)


@receiver(pre_social_login)
def sync_lesta_player(sender, request, sociallogin, **kwargs):
    """
    Создать или обновить Player при входе через Lesta.

    Автоматически синхронизирует игровой аккаунт с моделью Player.

    Args:
        sender: Отправитель сигнала
        request: Django request объект
        sociallogin: SocialLogin instance
        **kwargs: Дополнительные параметры
    """
    if sociallogin.account.provider != 'lesta':
        return  # Обрабатываем только Lesta аккаунты

    try:
        account_id = sociallogin.account.uid
        nickname = sociallogin.account.extra_data.get('nickname')

        if not account_id or not nickname:
            logger.warning("Missing account_id or nickname in Lesta social login")
            return

        # Создаём или обновляем Player
        player, created = Player.objects.update_or_create(
            accountDBID=account_id,
            defaults={
                'real_name': nickname,
                'name': nickname,  # Используем nickname как name (login)
            }
        )

        if created:
            logger.info(
                f"Created Player {player.id} for Lesta account {account_id} "
                f"(nickname: {nickname})"
            )
        else:
            logger.info(
                f"Updated Player {player.id} nickname to {nickname} "
                f"(account_id: {account_id})"
            )

    except Exception as e:
        # Не ломаем процесс авторизации если не удалось синхронизировать Player
        logger.error(
            f"Failed to sync Lesta player: {e}",
            exc_info=True,
            extra={
                'account_id': sociallogin.account.uid,
                'provider': sociallogin.account.provider,
            }
        )


@receiver(social_account_updated)
def update_user_nickname(sender, request, sociallogin, **kwargs):
    """
    Обновить никнейм пользователя при входе через Lesta.

    Синхронизирует first_name с актуальным никнеймом из игры.

    Args:
        sender: Отправитель сигнала
        request: Django request объект
        sociallogin: SocialLogin instance
        **kwargs: Дополнительные параметры
    """
    if sociallogin.account.provider != 'lesta':
        return  # Обрабатываем только Lesta аккаунты

    try:
        user = sociallogin.user
        nickname = sociallogin.account.extra_data.get('nickname')

        if nickname and user.first_name != nickname:
            user.first_name = nickname
            user.save(update_fields=['first_name'])

            logger.info(
                f"Updated user {user.id} first_name to {nickname}"
            )

    except Exception as e:
        logger.error(
            f"Failed to update user nickname: {e}",
            exc_info=True,
            extra={
                'user_id': sociallogin.user.id if sociallogin.user else None,
            }
        )


@receiver(user_logged_out)
def lesta_logout(sender, request, user, **kwargs):
    """
    Инвалидировать Lesta токен при выходе пользователя.

    Отправляет запрос к Lesta API для удаления access_token.

    Args:
        sender: Отправитель сигнала
        request: Django request объект
        user: Django User instance
        **kwargs: Дополнительные параметры
    """
    if not user:
        return

    try:
        # Получаем Lesta токен
        token = SocialToken.objects.filter(
            account__user=user,
            account__provider='lesta'
        ).first()

        if not token:
            return  # У пользователя нет Lesta токена

        # Инвалидируем токен на стороне Lesta
        try:
            client = LestaAPIClient()
            success = client.logout(token.token)

            if success:
                logger.info(f"Successfully invalidated Lesta token for user {user.id}")
            else:
                logger.warning(f"Failed to invalidate Lesta token for user {user.id}")

        except Exception as e:
            # Не критично если не удалось инвалидировать токен
            logger.error(
                f"Error invalidating Lesta token for user {user.id}: {e}",
                exc_info=True
            )

        # Удаляем токен из базы в любом случае
        token.delete()
        logger.debug(f"Deleted Lesta token from database for user {user.id}")

    except Exception as e:
        logger.error(
            f"Error in lesta_logout signal handler for user {user.id}: {e}",
            exc_info=True
        )
