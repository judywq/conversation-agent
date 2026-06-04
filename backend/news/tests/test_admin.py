# ruff: noqa: SLF001

from django.contrib import admin

from backend.news.models import NewsArticle
from backend.news.models import NewsClassification


def test_news_models_are_registered_in_admin():
    assert NewsArticle in admin.site._registry
    assert NewsClassification in admin.site._registry
