# replays/forms.py
import re

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django_comments.forms import CommentForm
from allauth.account.forms import SignupForm

from .models import ReplayVideoLink

User = get_user_model()


class SimpleCommentForm(CommentForm):
    name = forms.CharField(
        label="Имя",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Гость',
            'class': 'form-control'
        })
    )
    email = forms.EmailField(
        label='',
        required=False,
        widget=forms.HiddenInput()
    )
    url = forms.URLField(
        label='',
        required=False,
        widget=forms.HiddenInput()
    )
    comment = forms.CharField(
        label='Комментарий',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Напишите ваш комментарий...',
            'class': 'form-control'
        })
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(SimpleCommentForm, self).__init__(*args, **kwargs)

        if self.user and self.user.is_authenticated:
            name = self.user.first_name or self.user.username
            self.fields['name'].initial = name
            self.fields['name'].widget = forms.HiddenInput()

    def clean_email(self):
        """Возвращаем пустую строку для email"""
        return ''

    def clean_url(self):
        """Возвращаем пустую строку для url"""
        return ''

    def clean_name(self):
        """Если имя пустое, возвращаем 'Гость'"""
        name = self.cleaned_data.get('name', '').strip()
        if not name and (not self.user or not self.user.is_authenticated):
            return 'Гость'
        return name


class CustomSignupForm(SignupForm):
    """Кастомная форма регистрации с русскими сообщениями об ошибках."""

    def clean_username(self):
        """Проверка уникальности имени пользователя с русским сообщением об ошибке."""
        username = self.cleaned_data.get('username')
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                'Пользователь с таким именем уже существует. Пожалуйста, выберите другое имя.'
            )
        return username

    def clean_email(self):
        """Проверка уникальности email с русским сообщением об ошибке."""
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'Пользователь с таким email уже зарегистрирован. Пожалуйста, используйте другой email или войдите в существующий аккаунт.'
            )
        return email


class VideoLinkForm(forms.ModelForm):
    """Форма для добавления видео-ссылки к реплею."""

    VIDEO_URL_PATTERNS = {
        'youtube': [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?youtu\.be/[\w-]+',
        ],
        'vk': [
            r'(?:https?://)?(?:www\.)?vk\.com/video[\w.-]+',
            r'(?:https?://)?vk\.com/clip[\w.-]+',
            r'(?:https?://)?(?:www\.)?vkvideo\.ru/video[\w.-]+',
        ],
        'rutube': [
            r'(?:https?://)?rutube\.ru/video/[\w-]+',
        ],
    }

    class Meta:
        model = ReplayVideoLink
        fields = ['platform', 'url']
        widgets = {
            'platform': forms.Select(attrs={'class': 'form-control'}),
            'url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.youtube.com/watch?v=...',
            }),
        }

    def clean_url(self):
        url = self.cleaned_data.get('url', '').strip()
        platform = self.cleaned_data.get('platform')

        if platform and platform in self.VIDEO_URL_PATTERNS:
            patterns = self.VIDEO_URL_PATTERNS[platform]
            if not any(re.match(p, url) for p in patterns):
                platform_name = dict(ReplayVideoLink.PLATFORM_CHOICES).get(platform, platform)
                raise ValidationError(
                    f'Ссылка не похожа на видео с {platform_name}. '
                    f'Проверьте правильность URL.'
                )
        return url


class UsernameChangeForm(forms.Form):
    """Форма для изменения никнейма пользователя."""
    username = forms.CharField(
        label='Никнейм',
        max_length=150,
        min_length=3,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите новый никнейм',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['username'].initial = user.username

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if self.user and username == self.user.username:
            return username
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('Пользователь с таким именем уже существует.')
        return username


class AvatarUploadForm(forms.Form):
    """Форма для загрузки аватара."""
    avatar = forms.ImageField(
        label='Аватар',
        help_text='JPG или PNG, максимум 2 МБ, минимум 100x100 пикселей',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png'}),
    )

    def clean_avatar(self):
        image = self.cleaned_data.get('avatar')
        if image:
            if image.size > 2 * 1024 * 1024:
                raise ValidationError('Размер файла не должен превышать 2 МБ.')
            # Проверяем реальный формат через Pillow
            from PIL import Image as PILImage
            image.seek(0)
            try:
                img = PILImage.open(image)
                img.verify()  # проверяем целостность
            except Exception:
                raise ValidationError('Не удалось прочитать изображение. Убедитесь, что файл не повреждён.')
            image.seek(0)
            img = PILImage.open(image)
            if img.format not in ('JPEG', 'PNG', 'MPO'):
                raise ValidationError(f'Допустимые форматы: JPG, PNG. Ваш файл: {img.format}.')
            image.seek(0)
        return image