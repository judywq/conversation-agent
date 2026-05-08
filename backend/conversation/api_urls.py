from django.urls import path

from backend.conversation.api_views import CefrTopicSamplesView
from backend.conversation.api_views import SpeechToTextView
from backend.conversation.api_views import UserAudioUploadView

urlpatterns = [
    path("cefr-samples/", CefrTopicSamplesView.as_view(), name="conversation-cefr-samples"),
    path("stt/", SpeechToTextView.as_view(), name="conversation-stt"),
    path("user-audio/", UserAudioUploadView.as_view(), name="conversation-user-audio"),
]

