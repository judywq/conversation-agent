import json

import pytest
from django.urls import reverse

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.argument_summary import _clamp_text
from backend.conversation.services.argument_summary import build_argument_summary_prompt
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.argument_summary import format_argument_summary_bullets
from backend.conversation.services.argument_summary import get_argument_summary_bullets_for_agent
from backend.conversation.services.argument_summary import parse_argument_summary_response


@pytest.mark.django_db
def test_build_numbered_transcript_includes_speakers(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Campus life")
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I think dorms help freshmen make friends.",
        turn_index=1,
    )
    TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="That may be true, but commuting saves money.",
        turn_index=2,
    )

    transcript = build_numbered_transcript(session)

    assert "Turn 1" in transcript
    assert "Turn 2" in transcript
    assert "dorms help freshmen" in transcript
    assert "commuting saves money" in transcript


def test_parse_argument_summary_response_normalizes_claim_packages() -> None:
    raw = json.dumps(
        {
            "claims": [
                {
                    "text": "Dorms build community",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Shared meals daily contact"},
                            "explanations": [
                                {"type": "fact", "text": "Eat together in halls"},
                            ],
                        },
                        {
                            "type": "counterargument",
                            "reason": {"text": "Commuting cheaper"},
                            "explanations": [
                                {"type": "data", "text": "Dorm over twelve thousand"},
                            ],
                        },
                    ],
                },
            ],
        },
    )

    parsed = parse_argument_summary_response(raw)

    assert len(parsed["claims"]) == 1
    claim = parsed["claims"][0]
    assert claim["text"] == "Dorms build community"
    assert claim["arguments"][0]["type"] == "argument"
    assert claim["arguments"][0]["reason"]["text"] == "Shared meals daily contact"
    assert claim["arguments"][0]["explanations"][0]["type"] == "fact"
    assert claim["arguments"][1]["type"] == "counterargument"


def test_parse_argument_summary_migrates_legacy_threads() -> None:
    raw = json.dumps(
        {
            "argument_threads": [
                {
                    "claim": {"text": "Living on campus helps freshmen"},
                    "grounds": [
                        {
                            "text": "Shared meals create contact",
                            "supporting_facts": ["Students eat in dining halls"],
                        },
                    ],
                    "rebuttals": [
                        {
                            "counterargument": {"text": "Commuting is cheaper"},
                            "response": {"text": "", "speaker": ""},
                        },
                    ],
                },
            ],
        },
    )

    parsed = parse_argument_summary_response(raw)

    assert len(parsed["claims"]) == 1
    packages = parsed["claims"][0]["arguments"]
    assert packages[0]["type"] == "argument"
    assert packages[0]["reason"]["text"] == "Shared meals create contact"
    assert packages[1]["type"] == "counterargument"


def test_clamp_text_limits_words_and_chars() -> None:
    long_text = "one two three four five six seven eight nine ten eleven"
    clamped = _clamp_text(long_text)
    assert len(clamped.split()) <= 8
    assert len(clamped) <= 60


def test_format_argument_summary_bullets_renders_compact_nested_points() -> None:
    bullets = format_argument_summary_bullets(
        {
            "status": "ready",
            "claims": [
                {
                    "text": "Dorms build community",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Shared meals daily contact"},
                            "explanations": [
                                {"type": "fact", "text": "Eat together in halls"},
                            ],
                        },
                        {
                            "type": "counterargument",
                            "reason": {"text": "Commuting cheaper"},
                            "explanations": [
                                {"type": "data", "text": "Dorm over $12k/year"},
                            ],
                        },
                    ],
                },
            ],
        },
    )

    assert "- Dorms build community" in bullets
    assert "  - For: Shared meals daily contact" in bullets
    assert "    - Fact: Eat together in halls" in bullets
    assert "  - Against: Commuting cheaper" in bullets
    assert "    - Data: Dorm over $12k/year" in bullets


@pytest.mark.django_db
def test_get_argument_summary_bullets_for_agent_uses_ready_summary(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus life",
        argument_summary={
            "status": "ready",
            "claims": [
                {
                    "text": "Dorms build community",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Shared meals daily contact"},
                            "explanations": [],
                        },
                    ],
                },
            ],
        },
    )

    bullets = get_argument_summary_bullets_for_agent(session)

    assert "Dorms build community" in bullets
    assert "For: Shared meals daily contact" in bullets


@pytest.mark.django_db
def test_build_argument_summary_prompt_includes_previous_summary(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus life",
        argument_summary={
            "status": "ready",
            "claims": [
                {
                    "text": "Dorms build community",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Shared meals daily contact"},
                            "explanations": [],
                        },
                    ],
                },
            ],
        },
    )
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I think dorms help freshmen make friends.",
        turn_index=1,
    )

    prompt = build_argument_summary_prompt(session=session)

    assert "Dorms build community" in prompt
    assert "Previous summary" in prompt
    assert "Turn 1" in prompt


@pytest.mark.django_db
def test_argument_summary_signal_schedules_refresh(user, monkeypatch) -> None:
    scheduled: list[int] = []

    def _capture(session_id: int) -> None:
        scheduled.append(session_id)

    monkeypatch.setattr(
        "backend.conversation.argument_summary_signals.schedule_argument_summary_refresh_for_session_id",
        _capture,
    )

    session = ConversationSession.objects.create(user=user, topic="Campus life")
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I think dorms help freshmen make friends.",
        turn_index=1,
    )

    assert scheduled == [session.id]


@pytest.mark.django_db
def test_session_argument_summary_api_returns_ready_payload(user, client) -> None:
    session = ConversationSession.objects.create(user=user, topic="AI in schools")
    session.argument_summary = {
        "status": "ready",
        "claims": [
            {
                "text": "AI helps personalized learning",
                "arguments": [
                    {
                        "type": "argument",
                        "reason": {"text": "Adaptive feedback saves time"},
                        "explanations": [],
                    },
                ],
            },
        ],
    }
    session.save(update_fields=["argument_summary"])

    client.force_login(user)
    url = reverse("conversation-session-argument-summary", kwargs={"session_id": session.id})
    response = client.get(url)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["claims"][0]["text"] == "AI helps personalized learning"


@pytest.mark.django_db
def test_session_argument_summary_api_rejects_other_users(client) -> None:
    from backend.users.tests.factories import UserFactory

    owner = UserFactory()
    other = UserFactory()
    session = ConversationSession.objects.create(user=owner, topic="Private topic")
    client.force_login(other)

    url = reverse("conversation-session-argument-summary", kwargs={"session_id": session.id})
    response = client.get(url)

    assert response.status_code == 404
