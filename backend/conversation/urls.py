from django.contrib.auth.views import LogoutView
from django.urls import path

from backend.conversation.views import DiscussionLoginView
from backend.conversation.views import DiscussionSetupView

app_name = "conversation"

urlpatterns = [
    path("login/", DiscussionLoginView.as_view(), name="discussion-login"),
    path("logout/", LogoutView.as_view(next_page="conversation:discussion-login"), name="discussion-logout"),
    path("setup/", DiscussionSetupView.as_view(), name="discussion-setup"),
]
