"""
URL configuration for lesta_replays project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.static import serve
from lesta_replays import settings
from replays.models import Replay


class ReplaySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Replay.objects.filter(is_public=True)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


sitemaps = {"replays": ReplaySitemap}

urlpatterns = [
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("comments/", include("django_comments_xtd.urls")),
    path('adminn/', admin.site.urls),
    path("", include("replays.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path('static/<path:path>', serve, {
            'document_root': settings.STATIC_ROOT,
        }),
    ]