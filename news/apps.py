# news/apps.py
from django.apps import AppConfig


class NewsConfig(AppConfig):
    """
    Конфигурация приложения News.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'news'
    verbose_name = 'Новости'
