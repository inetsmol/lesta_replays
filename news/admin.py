# news/admin.py
from django.contrib import admin

from .models import News


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели News.
    """
    list_display = ('title', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'text')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'text', 'image')
        }),
        ('Настройки', {
            'fields': ('is_active',)
        }),
    )
