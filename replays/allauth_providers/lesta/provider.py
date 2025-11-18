# replays/allauth_providers/lesta/provider.py
"""Lesta Games provider для django-allauth."""

from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class LestaAccount(ProviderAccount):
    """Представление аккаунта Lesta Games."""

    def get_profile_url(self):
        """
        Получить URL профиля игрока на официальном сайте Lesta.

        Returns:
            str: URL профиля или None
        """
        account_id = self.account.uid
        if account_id:
            return f"https://tanki.su/ru/community/accounts/{account_id}/"
        return None

    def get_avatar_url(self):
        """
        Получить URL аватара пользователя.

        Lesta API не возвращает аватар, используем дефолтный.

        Returns:
            None
        """
        return None

    def to_str(self):
        """
        Строковое представление аккаунта.

        Returns:
            str: Никнейм игрока или дефолтное значение
        """
        dflt = super(LestaAccount, self).to_str()
        return self.account.extra_data.get('nickname', dflt)


class LestaProvider(OAuth2Provider):
    """OAuth2 провайдер для Lesta Games OpenID."""

    id = 'lesta'
    name = 'Lesta Games'
    account_class = LestaAccount

    def extract_uid(self, data):
        """
        Извлечь уникальный ID пользователя из данных callback.

        Args:
            data: Словарь с данными от Lesta API

        Returns:
            str: account_id пользователя
        """
        return str(data['account_id'])

    def extract_common_fields(self, data):
        """
        Извлечь общие поля для модели User.

        Args:
            data: Словарь с данными от Lesta API

        Returns:
            dict: Поля для создания/обновления User
        """
        nickname = data.get('nickname', '')

        return {
            'username': nickname,
            'first_name': nickname,
            # Lesta не возвращает email - будет запрошен у пользователя
        }

    def extract_email_addresses(self, data):
        """
        Извлечь email адреса из данных.

        Lesta API не возвращает email, поэтому возвращаем пустой список.
        Django-allauth автоматически запросит email у пользователя.

        Args:
            data: Словарь с данными от Lesta API

        Returns:
            list: Пустой список (email не предоставляется API)
        """
        return []

    def get_default_scope(self):
        """
        Получить список scopes по умолчанию.

        Lesta API не использует scopes (это не стандартный OAuth2).

        Returns:
            list: Пустой список
        """
        return []


provider_classes = [LestaProvider]
