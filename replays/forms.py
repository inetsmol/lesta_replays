# replays/forms.py
from django import forms
from django_comments.forms import CommentForm


class SimpleCommentForm(CommentForm):
    """
    Упрощенная форма комментариев для анонимных пользователей.
    Содержит только поля: имя (необязательное) и текст комментария.
    """

    # Переопределяем поле name, делаем его необязательным
    name = forms.CharField(
        label="Имя",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Гость',
            'class': 'form-control'
        })
    )

    # Убираем email и url полностью
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

    # Переопределяем поле comment
    comment = forms.CharField(
        label='Комментарий',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Напишите ваш комментарий...',
            'class': 'form-control'
        })
    )

    def clean_email(self):
        """Возвращаем пустую строку для email"""
        return ''

    def clean_url(self):
        """Возвращаем пустую строку для url"""
        return ''

    def clean_name(self):
        """Если имя пустое, возвращаем 'Гость'"""
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            return 'Гость'
        return name