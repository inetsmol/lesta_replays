# replays/allauth_providers/lesta/urls.py
"""URL patterns для Lesta provider."""

from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns
from .provider import LestaProvider

urlpatterns = default_urlpatterns(LestaProvider)
