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

    def get_oauth2_adapter(self, request):
        """
        Получить экземпляр OAuth2 адаптера.

        Args:
            request: Django request объект

        Returns:
            LestaOAuth2Adapter: Экземпляр адаптера
        """
        from .views import LestaOAuth2Adapter
        return LestaOAuth2Adapter(request)

    def redirect(self, request, process, next_url=None, data=None, **kwargs):
        """
        Выполнить редирект на страницу авторизации Lesta.

        Args:
            request: Django request объект
            process: Тип процесса ('login' или 'connect')
            next_url: URL для редиректа после авторизации
            data: Дополнительные данные
            **kwargs: Дополнительные параметры

        Returns:
            HttpResponseRedirect: Редирект на страницу авторизации Lesta
        """
        from django.http import HttpResponseRedirect
        from .client import LestaAPIClient
        from django.urls import reverse

        # Формируем callback URL
        callback_path = reverse('lesta_callback')
        callback_url = request.build_absolute_uri(callback_path)

        # Получаем URL для авторизации через LestaAPIClient
        client = LestaAPIClient()
        authorize_url = client.get_login_url(redirect_uri=callback_url)

        return HttpResponseRedirect(authorize_url)

    def get_default_scope(self):
        """
        Получить список scopes по умолчанию.

        Lesta API не использует scopes (это не стандартный OAuth2).

        Returns:
            list: Пустой список
        """
        return []

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
        account_id = data.get('account_id', '')

        # Генерируем фейковый email из account_id
        # Django требует email, но Lesta его не предоставляет
        fake_email = f"lesta_{account_id}@noreply.tanki.su"

        return {
            'username': nickname,
            'first_name': nickname,
            'email': fake_email,
        }

    def extract_email_addresses(self, data):
        """
        Извлечь email адреса из данных.

        Lesta API не возвращает email, поэтому генерируем фейковый email.
        Это позволяет избежать запроса email у пользователя при регистрации.

        Args:
            data: Словарь с данными от Lesta API

        Returns:
            list: Список с одним фейковым email адресом
        """
        from allauth.account.models import EmailAddress

        account_id = data.get('account_id', '')
        fake_email = f"lesta_{account_id}@noreply.tanki.su"

        # Возвращаем EmailAddress объект с неподтверждённым email
        return [EmailAddress(email=fake_email, verified=False, primary=True)]


provider_classes = [LestaProvider]
