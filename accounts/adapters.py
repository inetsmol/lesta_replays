# accounts/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Адаптер для автоматической связи OAuth с существующими аккаунтами
    """

    def pre_social_login(self, request, sociallogin):
        """
        КРИТИЧНО: Автосвязывание аккаунтов даже если email не подтвержден
        """
        # Если пользователь уже залогинен - ничего не делаем
        if request.user.is_authenticated:
            return

        # Получаем email из данных социального аккаунта
        email = sociallogin.account.extra_data.get('email', '').strip().lower()

        if not email:
            return

        try:
            User = get_user_model()

            # Ищем существующего пользователя с таким email
            user = User.objects.filter(email__iexact=email).first()

            if user:
                # АВТОМАТИЧЕСКИ ПОДТВЕРЖДАЕМ EMAIL
                email_address, created = EmailAddress.objects.get_or_create(
                    user=user,
                    email__iexact=email,
                    defaults={
                        'email': email,
                        'verified': True,  # Подтверждаем!
                        'primary': True,
                    }
                )

                # Если запись уже была, но не подтверждена - подтверждаем
                if not created and not email_address.verified:
                    email_address.verified = True
                    email_address.primary = True
                    email_address.save()

                # Связываем социальный аккаунт с существующим пользователем
                sociallogin.connect(request, user)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in pre_social_login: {e}")

    def save_user(self, request, sociallogin, form=None):
        """
        Для НОВЫХ пользователей через OAuth - сразу подтверждаем email
        """
        user = super().save_user(request, sociallogin, form)

        # Автоматически подтверждаем email для новых OAuth пользователей
        if user.email:
            email_address, created = EmailAddress.objects.get_or_create(
                user=user,
                email__iexact=user.email,
                defaults={
                    'email': user.email.lower(),
                    'verified': True,
                    'primary': True,
                }
            )

            if not created and not email_address.verified:
                email_address.verified = True
                email_address.primary = True
                email_address.save()

        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Разрешить автоматическую регистрацию
        """
        return True