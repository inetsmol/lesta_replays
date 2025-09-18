from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import ReplayListView, ReplayUploadView, ReplayDetailView, ReplayDownloadView

urlpatterns = [
    path('', ReplayListView.as_view(), name='replay_list'),
    path('<int:pk>/', ReplayDetailView.as_view(), name='replay_detail'),
    path('upload/', ReplayUploadView.as_view(), name='replay_upload'),
    path("download/<int:replay_id>/", ReplayDownloadView.as_view(), name="replay_download"),
    # Если хотите поддержать ссылку без завершающего слэша (как у вас), добавьте и этот:
    path("download/<int:replay_id>", ReplayDownloadView.as_view()),
]

# dev-раздача файлов /files/<file_name>
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)