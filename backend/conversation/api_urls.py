from django.urls import path

from backend.conversation.api_views import SpeechToTextView

urlpatterns = [
    path("stt/", SpeechToTextView.as_view(), name="conversation-stt"),
]

