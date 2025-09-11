from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import replay_detail, ReplayListView

urlpatterns = [
    path('', ReplayListView.as_view(), name='replay_list'),
    # path('<int:pk>/', ReplayDetailView.as_view(), name='replay_detail'),
    path("<int:pk>/", replay_detail, name="replay_detail"),
]

# dev-раздача файлов /files/<file_name>
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)