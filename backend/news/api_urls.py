from django.urls import path

from backend.news.api_views import ClassifiedArticleListView

urlpatterns = [
    path(
        "classified-articles/",
        ClassifiedArticleListView.as_view(),
        name="news-classified-articles",
    ),
]
