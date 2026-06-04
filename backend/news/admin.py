from django.contrib import admin

from .models import NewsArticle
from .models import NewsClassification


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "feed_title",
        "status",
        "published_at",
        "fetched_at",
    )
    list_filter = ("status", "feed_title")
    search_fields = ("title", "summary", "url", "feed_title")
    readonly_fields = ("created_at", "updated_at", "fetched_at")


@admin.register(NewsClassification)
class NewsClassificationAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "taxonomy_version",
        "main_category",
        "status",
        "is_suitable",
        "confidence",
        "classified_at",
    )
    list_filter = ("taxonomy_version", "main_category", "status", "is_suitable")
    search_fields = ("article__title", "main_category", "rationale")
    readonly_fields = ("created_at", "updated_at", "classified_at")
