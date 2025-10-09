# accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from .models import Profile
import re

User = get_user_model()


class CustomSignupForm(forms.Form):
    """
    Кастомная форма регистрации без наследования от allauth
    """
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
        })
    )

    lesta_nickname = forms.CharField(
        label="Ник в игре",
        max_length=64,
        min_length=3,
        help_text="Это будет ваш логин для входа",
        widget=forms.TextInput(attrs={
            'placeholder': 'Ваш игровой ник',
            'autocomplete': 'username',
        })
    )

    clan = forms.CharField(
        label="Клан",
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ваш клан (необязательно)'
        })
    )

    password1 = forms.CharField(
        label="Пароль",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Придумайте надежный пароль',
            'autocomplete': 'new-password',
        })
    )

    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Повторите пароль',
            'autocomplete': 'new-password',
        })
    )

    def clean_email(self):
        """Проверка уникальности email"""
        email = self.cleaned_data.get('email', '').lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже зарегистрирован")

        return email

    def clean_lesta_nickname(self):
        """Валидация игрового ника"""
        lesta_nickname = self.cleaned_data.get('lesta_nickname')

        if not lesta_nickname:
            raise forms.ValidationError("Введите игровой ник")

        # Проверка уникальности
        if User.objects.filter(username__iexact=lesta_nickname).exists():
            raise forms.ValidationError("Этот ник уже занят")

        # Валидация формата
        if not re.match(r'^[\w.@+-]+$', lesta_nickname):
            raise forms.ValidationError(
                "Ник может содержать только буквы, цифры и символы: . @ + - _"
            )

        return lesta_nickname

    def clean(self):
        """Общая валидация формы"""
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают")

        return cleaned_data

    def signup(self, request, user):
        """
        Метод, который вызывает allauth после создания пользователя
        """
        # Создаем профиль
        profile, created = Profile.objects.get_or_create(user=user)
        profile.lesta_nickname = self.cleaned_data['lesta_nickname']
        profile.clan = self.cleaned_data.get('clan', '')
        profile.save()

        return user