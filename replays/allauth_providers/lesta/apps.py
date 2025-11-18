# replays/allauth_providers/lesta/apps.py
"""App configuration для Lesta Games provider."""

from django.apps import AppConfig


class LestaProviderConfig(AppConfig):
    """Configuration для Lesta Games OAuth2 provider."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'replays.allauth_providers.lesta'
    label = 'lesta_provider'
    verbose_name = 'Lesta Games OAuth2 Provider'
