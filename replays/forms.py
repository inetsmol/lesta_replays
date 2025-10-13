# replays/forms.py
from django import forms
from django_comments.forms import CommentForm


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