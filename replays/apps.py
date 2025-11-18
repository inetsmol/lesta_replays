# replays/apps.py
"""Конфигурация приложения replays."""

from django.apps import AppConfig


class ReplaysConfig(AppConfig):
    """Конфигурация приложения replays."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'replays'

    def ready(self):
        """
        Метод вызывается когда приложение готово к работе.

        Импортирует signal handlers для их регистрации.
        """
        import replays.signals  # noqa: F401
