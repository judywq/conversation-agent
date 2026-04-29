from django.urls import path

from backend.conversation.api_views import CefrTopicSamplesView
from backend.conversation.api_views import SpeechToTextView

urlpatterns = [
    path("cefr-samples/", CefrTopicSamplesView.as_view(), name="conversation-cefr-samples"),
    path("stt/", SpeechToTextView.as_view(), name="conversation-stt"),
]

