from django.urls import path

from backend.conversation.api_views import AgentCharactersView
from backend.conversation.api_views import CefrTopicSamplesView
from backend.conversation.api_views import DiscussionScenarioView
from backend.conversation.api_views import SessionArgumentSummaryView
from backend.conversation.api_views import SessionDetailView
from backend.conversation.api_views import SessionListView
from backend.conversation.api_views import SpeechToTextView
from backend.conversation.api_views import UserAudioUploadView

urlpatterns = [
    path("characters/", AgentCharactersView.as_view(), name="conversation-characters"),
    path("cefr-samples/", CefrTopicSamplesView.as_view(), name="conversation-cefr-samples"),
    path(
        "discussion-scenario/",
        DiscussionScenarioView.as_view(),
        name="conversation-discussion-scenario",
    ),
    path("sessions/", SessionListView.as_view(), name="conversation-session-list"),
    path(
        "sessions/<int:session_id>/",
        SessionDetailView.as_view(),
        name="conversation-session-detail",
    ),
    path(
        "sessions/<int:session_id>/argument-summary/",
        SessionArgumentSummaryView.as_view(),
        name="conversation-session-argument-summary",
    ),
    path("stt/", SpeechToTextView.as_view(), name="conversation-stt"),
    path("user-audio/", UserAudioUploadView.as_view(), name="conversation-user-audio"),
]

