from __future__ import annotations

from django.db import models

from backend.core.models import TimestampedBase


class NewsArticle(TimestampedBase):
    class Status(models.TextChoices):
        IMPORTED = "imported", "Imported"
        HIDDEN = "hidden", "Hidden"

    miniflux_entry_id = models.PositiveBigIntegerField(unique=True)
    miniflux_feed_id = models.PositiveBigIntegerField()
    feed_title = models.CharField(max_length=255)
    source_title = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    full_text = models.TextField(blank=True, default="")
    url = models.URLField(max_length=1000)
    normalized_url = models.URLField(max_length=1000, unique=True)
    published_at = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.IMPORTED,
    )
    raw_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-published_at", "-id")
        indexes = [
            models.Index(
                fields=("status", "-published_at"),
                name="news_article_status_pub_idx",
            ),
            models.Index(
                fields=("miniflux_feed_id", "-published_at"),
                name="news_article_feed_pub_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class NewsClassification(TimestampedBase):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    article = models.ForeignKey(
        NewsArticle,
        on_delete=models.CASCADE,
        related_name="classifications",
    )
    taxonomy_version = models.CharField(max_length=32)
    main_category = models.CharField(max_length=100, blank=True)
    subtopics = models.JSONField(default=list, blank=True)
    cefr_level = models.CharField(max_length=8, blank=True)
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
    )
    rationale = models.TextField(blank=True)
    llm_model = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.SUCCEEDED,
    )
    error_message = models.TextField(blank=True)
    raw_output = models.JSONField(default=dict, blank=True)
    classified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-classified_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("article", "taxonomy_version"),
                name="unique_news_classification_per_taxonomy",
            ),
        ]
        indexes = [
            models.Index(
                fields=("taxonomy_version", "main_category", "status"),
                name="news_class_lookup_idx",
            ),
        ]

    @property
    def is_ready_for_learning(self) -> bool:
        return self.status == self.Status.SUCCEEDED

    def __str__(self) -> str:
        return f"{self.article_id}:{self.taxonomy_version}:{self.main_category}"
