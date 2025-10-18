# replays/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django_comments.forms import CommentForm
from allauth.account.forms import SignupForm

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