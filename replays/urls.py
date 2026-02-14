from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    ReplayListView, ReplayDetailView, ReplayDownloadView, AboutView, ReplayFiltersView,
    health, ReplayBatchUploadView, MyReplaysView, ReplayDeleteView, ReplayVoteView, get_replay_info,
    ReplayUpdateDescriptionView, SubscriptionInfoView, AddVideoLinkView, RemoveVideoLinkView,
    UploadAvatarView,
)

urlpatterns = [
    path('', ReplayListView.as_view(), name='replay_list'),
    path('replays/my/', MyReplaysView.as_view(), name='my_replay_list'),
    path('replays/<int:pk>/', ReplayDetailView.as_view(), name='replay_detail'),
    path('replays/<int:pk>/delete/', ReplayDeleteView.as_view(), name='replay_delete'),
    path('replays/<int:pk>/update_description/', ReplayUpdateDescriptionView.as_view(), name='replay_update_description'),
    path('replays/<int:pk>/vote/', ReplayVoteView.as_view(), name='replay_vote'),
    path("replays/filters/", ReplayFiltersView.as_view(), name="replay_filters"),
    path('replays/upload/', ReplayBatchUploadView.as_view(), name='replay_upload'),
    path('replays/<int:pk>/add-video/', AddVideoLinkView.as_view(), name='replay_add_video'),
    path('replays/video/<int:pk>/remove/', RemoveVideoLinkView.as_view(), name='replay_remove_video'),
    path('subscription/', SubscriptionInfoView.as_view(), name='subscription_info'),
    path('profile/avatar/', UploadAvatarView.as_view(), name='upload_avatar'),
    path('api/replay/', get_replay_info, name='api_replay_info'),
    path('<int:pk>/download/', ReplayDownloadView.as_view(), name='replay_download'),
    path("about/", AboutView.as_view(), name="about"),
    path('health/', health, name='health'),
]

# dev-раздача файлов /files/<file_name>
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)