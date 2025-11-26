# news/forms.py
from django import forms
from .models import News


class NewsForm(forms.ModelForm):
    """
    Форма для создания и редактирования новостей.
    """
    class Meta:
        model = News
        fields = ['title', 'text', 'image', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-800 text-white rounded-lg border border-gray-700 focus:border-yellow-500 focus:outline-none',
                'placeholder': 'Заголовок новости'
            }),
            'text': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 bg-gray-800 text-white rounded-lg border border-gray-700 focus:border-yellow-500 focus:outline-none',
                'rows': 10,
                'placeholder': 'Текст новости'
            }),
            'image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 bg-gray-800 text-white rounded-lg border border-gray-700 focus:border-yellow-500 focus:outline-none',
                'accept': 'image/*'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-yellow-500 bg-gray-800 border-gray-700 rounded focus:ring-yellow-500'
            }),
        }
