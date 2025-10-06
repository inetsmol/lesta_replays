from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import ReplayListView, ReplayDetailView, ReplayDownloadView, AboutView, ReplayFiltersView, \
    health, ReplayBatchUploadView

urlpatterns = [
    path('', ReplayListView.as_view(), name='replay_list'),
    path('replays/<int:pk>/', ReplayDetailView.as_view(), name='replay_detail'),
    path("replays/filters/", ReplayFiltersView.as_view(), name="replay_filters"),
    path('replays/upload/', ReplayBatchUploadView.as_view(), name='replay_upload'),
    path('<int:pk>/download/', ReplayDownloadView.as_view(), name='replay_download'),
    path("about/", AboutView.as_view(), name="about"),
    path('health/', health, name='health'),
]

# dev-раздача файлов /files/<file_name>
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)