import json

# ruff: noqa: E501
from types import SimpleNamespace

import pytest
from django.utils import timezone

from backend.news.classifier import classify_article
from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.taxonomy import TAXONOMY_VERSION


class FakeLLM:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content)


@pytest.fixture
def article(db):
    return NewsArticle.objects.create(
        miniflux_entry_id=1001,
        miniflux_feed_id=5,
        feed_title="NPR Topics: Technology",
        title="AI tutors enter classrooms",
        summary="Schools are testing AI tutors.",
        url="https://example.com/ai-tutors",
        normalized_url="https://example.com/ai-tutors",
        published_at=timezone.now(),
    )


@pytest.mark.django_db
def test_classify_article_stores_valid_llm_output(article):
    llm = FakeLLM(
        json.dumps(
            {
                "main_category": "technology-ai",
                "subtopics": ["ai-teachers"],
                "cefr_level": "B1",
                "is_suitable": True,
                "confidence": 0.87,
                "rationale": "It discusses AI tutors in classrooms.",
            },
        ),
    )

    classification = classify_article(article, llm=llm, llm_model="fake-model")

    assert classification.status == NewsClassification.Status.SUCCEEDED
    assert classification.taxonomy_version == TAXONOMY_VERSION
    assert classification.main_category == "technology-ai"
    assert classification.subtopics == ["ai-teachers"]
    assert classification.is_ready_for_learning is True
    assert classification.llm_model == "fake-model"
    assert "AI tutors enter classrooms" in str(llm.messages[0].content)


@pytest.mark.django_db
def test_classify_article_accepts_json_wrapped_in_markdown_fence(article):
    llm = FakeLLM(
        "```json\n"
        + json.dumps(
            {
                "main_category": "technology-ai",
                "subtopics": ["ai-teachers"],
                "cefr_level": "B1",
                "is_suitable": True,
                "confidence": 0.87,
                "rationale": "It discusses AI tutors in classrooms.",
            },
        )
        + "\n```",
    )

    classification = classify_article(article, llm=llm, llm_model="fake-model")

    assert classification.status == NewsClassification.Status.SUCCEEDED
    assert classification.main_category == "technology-ai"


@pytest.mark.django_db
def test_classify_article_records_failure_for_malformed_json(article):
    classification = classify_article(article, llm=FakeLLM("not json"), llm_model="fake-model")

    assert classification.status == NewsClassification.Status.FAILED
    assert classification.is_ready_for_learning is False
    assert "JSON" in classification.error_message


@pytest.mark.django_db
def test_classify_article_rejects_unknown_taxonomy_values(article):
    llm = FakeLLM(
        json.dumps(
            {
                "main_category": "technology-ai",
                "subtopics": ["burnout"],
                "cefr_level": "B1",
                "is_suitable": True,
                "confidence": 0.7,
                "rationale": "Wrong subtopic category.",
            },
        ),
    )

    classification = classify_article(article, llm=llm, llm_model="fake-model")

    assert classification.status == NewsClassification.Status.FAILED
    assert "Unknown news subtopic" in classification.error_message


@pytest.mark.django_db
def test_classify_article_records_provider_failure(article):
    classification = classify_article(article, llm=FakeLLM(error=RuntimeError("provider down")), llm_model="fake-model")

    assert classification.status == NewsClassification.Status.FAILED
    assert "provider down" in classification.error_message
