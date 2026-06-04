import pytest

# ruff: noqa: E501
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.taxonomy import TAXONOMY_VERSION
from backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def authenticated_client():
    client = APIClient()
    client.force_authenticate(user=UserFactory())
    return client


def create_classified_article(
    *,
    title="AI tutors enter classrooms",
    main_category="technology-ai",
    subtopics=None,
    is_suitable=True,
    published_at=None,
):
    article = NewsArticle.objects.create(
        miniflux_entry_id=NewsArticle.objects.count() + 1,
        miniflux_feed_id=1,
        feed_title="NPR Topics: Technology",
        source_title="NPR Topics: Technology",
        source_url="https://www.npr.org/",
        title=title,
        summary="Schools are testing AI tutors.",
        url=f"https://example.com/{NewsArticle.objects.count() + 1}",
        normalized_url=f"https://example.com/{NewsArticle.objects.count() + 1}",
        published_at=published_at or timezone.now(),
    )
    NewsClassification.objects.create(
        article=article,
        taxonomy_version=TAXONOMY_VERSION,
        main_category=main_category,
        subtopics=subtopics or ["ai-teachers"],
        cefr_level="B1",
        is_suitable=is_suitable,
        confidence="0.800",
        rationale="Useful for learning.",
        status=NewsClassification.Status.SUCCEEDED,
    )
    return article


def test_classified_articles_endpoint_requires_authentication():
    response = APIClient().get(
        reverse("news-classified-articles"),
        {"category": "technology-ai"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_classified_articles_endpoint_filters_by_category(authenticated_client):
    article = create_classified_article()
    create_classified_article(title="Not suitable", is_suitable=False)
    create_classified_article(
        title="Business article",
        main_category="business-work-economy",
        subtopics=["startup-culture"],
    )

    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "technology-ai"},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert [item["id"] for item in payload["results"]] == [article.id]
    assert payload["results"][0]["source_title"] == "NPR Topics: Technology"
    assert payload["results"][0]["url"] == article.url


def test_classified_articles_endpoint_filters_by_subtopic(authenticated_client):
    matching = create_classified_article(subtopics=["ai-teachers"])
    create_classified_article(title="Deepfakes", subtopics=["deepfakes"])

    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "technology-ai", "subtopic": "ai-teachers"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.json()["results"]] == [matching.id]


def test_classified_articles_endpoint_returns_empty_result(authenticated_client):
    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "technology-ai"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"results": []}


def test_classified_articles_endpoint_rejects_missing_category(authenticated_client):
    response = authenticated_client.get(reverse("news-classified-articles"))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "category is required"


def test_classified_articles_endpoint_rejects_unknown_category(authenticated_client):
    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "unknown"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unknown news category" in response.json()["detail"]


def test_classified_articles_endpoint_rejects_unknown_subtopic(authenticated_client):
    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "technology-ai", "subtopic": "startup-culture"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unknown news subtopic" in response.json()["detail"]


def test_classified_articles_endpoint_orders_by_article_published_at(
    authenticated_client,
):
    base_time = timezone.now()
    old_article = create_classified_article(
        title="Old article",
        published_at=base_time,
    )
    new_article = create_classified_article(
        title="New article",
        published_at=base_time + timezone.timedelta(hours=1),
    )

    response = authenticated_client.get(
        reverse("news-classified-articles"),
        {"category": "technology-ai"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.json()["results"]] == [
        new_article.id,
        old_article.id,
    ]
