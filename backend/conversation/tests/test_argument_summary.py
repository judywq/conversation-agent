import json

import pytest
from django.urls import reverse

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.argument_summary import build_argument_summary_prompt
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.argument_summary import format_argument_summary_bullets
from backend.conversation.services.argument_summary import get_argument_summary_bullets_for_agent
from backend.conversation.services.argument_summary import mark_argument_summary_pending
from backend.conversation.services.argument_summary import merge_speaker_summaries
from backend.conversation.services.argument_summary import parse_argument_summary_response
from backend.conversation.services.turn_manager import decide_next_speaker


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


def test_parse_argument_summary_response_normalizes_speakers() -> None:
    raw = json.dumps(
        {
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claim": "Dorms build community",
                    "evidence": [
                        {"type": "fact", "text": "Shared meals daily contact"},
                        {"type": "data", "text": "Survey shows more friendships"},
                    ],
                },
                {
                    "speaker_id": "agent_1",
                    "speaker_name": "Lucas",
                    "speaker_type": "agent",
                    "claim": "Commuting is cheaper",
                    "evidence": [
                        {"type": "example", "text": "Saves housing meal plan costs"},
                    ],
                },
            ],
        },
    )

    parsed = parse_argument_summary_response(raw)

    assert len(parsed["speakers"]) == 2
    assert parsed["speakers"][0]["speaker_name"] == "Judy"
    assert parsed["speakers"][0]["claim"] == "Dorms build community"
    assert parsed["speakers"][1]["evidence"][0]["type"] == "example"


def test_merge_speaker_summaries_accumulates_evidence() -> None:
    previous = [
        {
            "speaker_id": "user",
            "speaker_name": "Judy",
            "speaker_type": "user",
            "claim": "Dorms help community",
            "evidence": [{"type": "fact", "text": "Shared meals"}],
        },
    ]
    new = [
        {
            "speaker_id": "user",
            "speaker_name": "Judy",
            "speaker_type": "user",
            "claim": "Dorms help freshmen build community",
            "evidence": [{"type": "data", "text": "70 percent made friends"}],
        },
        {
            "speaker_id": "agent_1",
            "speaker_name": "Lucas",
            "speaker_type": "agent",
            "claim": "Commuting saves money",
            "evidence": [],
        },
    ]

    merged = merge_speaker_summaries(previous, new)

    assert len(merged) == 2
    user = merged[0]
    assert user["claim"] == "Dorms help freshmen build community"
    assert len(user["evidence"]) == 2


def test_format_argument_summary_bullets_renders_speaker_stances() -> None:
    bullets = format_argument_summary_bullets(
        {
            "status": "ready",
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claim": "Dorms build community",
                    "evidence": [
                        {"type": "fact", "text": "Shared meals daily contact"},
                    ],
                },
            ],
        },
    )

    assert "- Judy: Dorms build community" in bullets
    assert "  - Fact: Shared meals daily contact" in bullets


@pytest.mark.django_db
def test_get_argument_summary_bullets_for_agent_uses_ready_summary(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus life",
        argument_summary={
            "status": "ready",
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claim": "Dorms build community",
                    "evidence": [],
                },
            ],
        },
    )

    bullets = get_argument_summary_bullets_for_agent(session)

    assert "Judy: Dorms build community" in bullets


@pytest.mark.django_db
def test_build_argument_summary_prompt_includes_previous_summary(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus life",
        argument_summary={
            "status": "ready",
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claim": "Dorms build community",
                    "evidence": [],
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
def test_mark_argument_summary_pending_preserves_speakers(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus life",
        argument_summary={
            "status": "ready",
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claim": "Dorms build community",
                    "evidence": [{"type": "fact", "text": "Shared meals"}],
                },
            ],
        },
    )

    mark_argument_summary_pending(session)
    session.refresh_from_db()

    assert session.argument_summary["status"] == "pending"
    assert session.argument_summary["speakers"][0]["claim"] == "Dorms build community"
    assert session.argument_summary["turn_count"] == session.turn_count


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
        "speakers": [
            {
                "speaker_id": "user",
                "speaker_name": "Judy",
                "speaker_type": "user",
                "claim": "AI helps personalized learning",
                "evidence": [],
            },
        ],
    }
    session.save(update_fields=["argument_summary"])

    client.force_login(user)
    url = reverse("conversation-session-argument-summary", kwargs={"session_id": session.id})
    response = client.get(url)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["speakers"][0]["claim"] == "AI helps personalized learning"


@pytest.mark.django_db
def test_named_question_at_turn_19_still_prefers_closing_agent(user) -> None:
    user.name = "Judy"
    user.save()
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=19, max_turns=20)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", display_name="Jack", personality={"persona_name": "Discussion Driver"}),
        ],
    )
    TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Do you like taking the school bus, Judy?",
        turn_index=18,
    )

    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)

    assert decision.terminate is False
    assert decision.next_speaker_type == "agent"
    assert decision.reason == "closing_agent_turn"
