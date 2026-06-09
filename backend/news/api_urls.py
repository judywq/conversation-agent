from django.urls import path

from backend.news.api_views import ClassifiedArticleListView
from backend.news.api_views import NewsTaxonomyView

urlpatterns = [
    path(
        "taxonomy/",
        NewsTaxonomyView.as_view(),
        name="news-taxonomy",
    ),
    path(
        "classified-articles/",
        ClassifiedArticleListView.as_view(),
        name="news-classified-articles",
    ),
]
