import json

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from backend.conversation.services.discussion_scenario import _parse_scenario_payload
from backend.news.taxonomy import serialize_taxonomy


def test_serialize_taxonomy_includes_categories_and_subtopics():
    payload = serialize_taxonomy()
    assert len(payload) == 8
    technology = next(item for item in payload if item["slug"] == "technology-ai")
    assert technology["name"] == "Technology & AI"
    assert any(sub["slug"] == "ai-teachers" for sub in technology["subtopics"])


def test_parse_scenario_payload_accepts_json_object():
    scenario = _parse_scenario_payload(
        json.dumps({"scenario": "Your school intends to introduce AI tutors. Do you agree?"}),
    )
    assert "AI tutors" in scenario


@pytest.mark.django_db
def test_news_taxonomy_api_returns_categories(user):
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(reverse("news-taxonomy"))
    assert response.status_code == 200
    assert response.json()["categories"]
    assert response.json()["taxonomy_version"] == "2026-06-03"


@pytest.mark.django_db
def test_discussion_scenario_api_validates_taxonomy(user, monkeypatch):
    client = APIClient()
    client.force_authenticate(user=user)

    def fake_generate(*, category: str, subtopic: str):
        assert category == "technology-ai"
        assert subtopic == "ai-teachers"
        from backend.conversation.services.discussion_scenario import DiscussionScenarioResult

        return DiscussionScenarioResult(
            scenario="Your school intends to introduce AI tutors to reduce personnel costs. Do you agree?",
            category=category,
            subtopic=subtopic,
            category_name="Technology & AI",
            subtopic_name="AI teachers",
        )

    monkeypatch.setattr(
        "backend.conversation.api_views.setup_discussion_context",
        fake_generate,
    )
    response = client.post(
        reverse("conversation-discussion-scenario"),
        {"category": "technology-ai", "subtopic": "ai-teachers"},
        format="json",
    )
    assert response.status_code == 200
    assert "AI tutors" in response.json()["scenario"]
