from django.urls import path

from .api_views import ActiveModelsView

urlpatterns = [
    path("models/", ActiveModelsView.as_view(), name="llm-active-models"),
]

