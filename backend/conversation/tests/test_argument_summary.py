import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.argument_summary import build_argument_summary_prompt
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.argument_summary import finalize_argument_summary_on_conclusion
from backend.conversation.services.argument_summary import format_argument_summary_bullets
from backend.conversation.services.argument_summary import get_argument_summary_bullets_for_agent
from backend.conversation.services.argument_summary import mark_argument_summary_pending
from backend.conversation.services.argument_summary import generate_argument_summary_for_session
from backend.conversation.services.argument_summary import merge_speaker_summaries
from backend.conversation.services.argument_summary import parse_argument_summary_response
from backend.conversation.services.argument_summary import _normalize_speaker
from backend.conversation.services.argument_summary import _speakers_from_summary
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn


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


def test_parse_argument_summary_response_normalizes_nested_speakers() -> None:
    raw = json.dumps(
        {
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claims": [
                        {
                            "text": "Dorms build community",
                            "reasons": [
                                {
                                    "text": "Shared meals create daily contact",
                                    "explanations": [
                                        {"type": "fact", "text": "Common dining halls"},
                                        {"type": "data", "text": "More friendships reported"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "speaker_id": "agent_1",
                    "speaker_name": "Lucas",
                    "speaker_type": "agent",
                    "claims": [
                        {
                            "text": "Commuting is cheaper",
                            "reasons": [
                                {
                                    "text": "Avoids housing and meal-plan fees",
                                    "explanations": [
                                        {"type": "example", "text": "Saves thousands per semester"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )

    parsed = parse_argument_summary_response(raw)

    assert len(parsed["speakers"]) == 2
    assert parsed["speakers"][0]["claims"][0]["text"] == "Dorms build community"
    assert parsed["speakers"][0]["claims"][0]["reasons"][0]["explanations"][1]["type"] == "data"
    assert parsed["speakers"][1]["claims"][0]["reasons"][0]["explanations"][0]["type"] == "example"


def test_normalize_speaker_migrates_flat_legacy_shape() -> None:
    speaker = _normalize_speaker(
        {
            "speaker_id": "user",
            "speaker_name": "Judy",
            "speaker_type": "user",
            "claim": "Dorms build community",
            "evidence": [
                {"turn": 2, "type": "fact", "text": "Shared meals daily contact"},
            ],
        },
    )

    assert speaker is not None
    assert speaker["claims"][0]["text"] == "Dorms build community"
    assert speaker["claims"][0]["reasons"][0]["text"] == "Shared meals daily contact"
    assert "turn" not in speaker["claims"][0]["reasons"][0]["explanations"][0]


def test_merge_speaker_summaries_updates_existing_claim_and_reason() -> None:
    previous = [
        {
            "speaker_id": "user",
            "speaker_name": "Judy",
            "speaker_type": "user",
            "claims": [
                {
                    "text": "Dorms help community",
                    "reasons": [
                        {
                            "text": "Shared meals",
                            "explanations": [{"type": "fact", "text": "Daily contact"}],
                        },
                    ],
                },
            ],
        },
    ]
    new = [
        {
            "speaker_id": "user",
            "speaker_name": "Judy",
            "speaker_type": "user",
            "claims": [
                {
                    "text": "Dorms help freshmen build community",
                    "reasons": [
                        {
                            "text": "Shared meals",
                            "explanations": [{"type": "data", "text": "70 percent made friends"}],
                        },
                    ],
                },
            ],
        },
        {
            "speaker_id": "agent_1",
            "speaker_name": "Lucas",
            "speaker_type": "agent",
            "claims": [
                {
                    "text": "Commuting saves money",
                    "reasons": [],
                },
            ],
        },
    ]

    merged = merge_speaker_summaries(previous, new)

    assert len(merged) == 2
    user = merged[0]
    assert user["claims"][0]["text"] == "Dorms help freshmen build community"
    assert len(user["claims"]) == 1
    assert len(user["claims"][0]["reasons"]) == 1
    assert len(user["claims"][0]["reasons"][0]["explanations"]) == 2


@pytest.mark.django_db
def test_generate_uses_parsed_speakers_without_remerge(user) -> None:
    previous_speakers = [
        {
            "speaker_id": "agent_1",
            "speaker_name": "Emma",
            "speaker_type": "agent",
            "claims": [
                {
                    "text": "Gaming alone still felt stressed",
                    "reasons": [
                        {
                            "text": "Avoiding friends prolongs stress",
                            "explanations": [
                                {"type": "example", "text": "gaming alone still felt stressed"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    session = ConversationSession.objects.create(user=user, topic="Coping methods")
    session.argument_summary = {"status": "ready", "speakers": previous_speakers}
    session.save(update_fields=["argument_summary"])
    TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Talking to friends helped me relax more than gaming alone.",
        turn_index=1,
    )

    parsed_speakers = [
        {
            "speaker_id": "agent_1",
            "speaker_name": "Emma",
            "speaker_type": "agent",
            "claims": [
                {
                    "text": "Mixed coping methods work best",
                    "reasons": [
                        {
                            "text": "Talking to others improves relaxation",
                            "explanations": [
                                {"type": "example", "text": "felt relaxed after talking"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]

    with patch(
        "backend.conversation.services.argument_summary.extract_argument_summary",
        return_value={"speakers": parsed_speakers},
    ):
        payload = generate_argument_summary_for_session(session)

    assert payload["status"] == "ready"
    assert payload["speakers"] == parsed_speakers
    assert len(payload["speakers"][0]["claims"]) == 1
    assert len(merge_speaker_summaries(previous_speakers, parsed_speakers)[0]["claims"]) == 2


def test_format_argument_summary_bullets_renders_nested_structure_without_turn_numbers() -> None:
    bullets = format_argument_summary_bullets(
        {
            "status": "ready",
            "speakers": [
                {
                    "speaker_id": "user",
                    "speaker_name": "Judy",
                    "speaker_type": "user",
                    "claims": [
                        {
                            "text": "Dorms build community",
                            "reasons": [
                                {
                                    "text": "Shared meals create contact",
                                    "explanations": [
                                        {"type": "fact", "text": "Common dining halls"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )

    assert "- Judy" in bullets
    assert "Claim: Dorms build community" in bullets
    assert "Reason: Shared meals create contact" in bullets
    assert "Fact: Common dining halls" in bullets
    assert "Turn " not in bullets


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
                    "claims": [
                        {
                            "text": "Dorms build community",
                            "reasons": [],
                        },
                    ],
                },
            ],
        },
    )

    bullets = get_argument_summary_bullets_for_agent(session)

    assert "Judy" in bullets
    assert "Claim: Dorms build community" in bullets


@pytest.mark.django_db
def test_build_argument_summary_prompt_includes_previous_summary_and_new_rules(user) -> None:
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
                    "claims": [
                        {
                            "text": "Dorms build community",
                            "reasons": [],
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
    assert "Previous speaker opinions" in prompt
    assert "valuable argumentation" in prompt
    assert "Do NOT include turn numbers" in prompt
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
                    "claims": [
                        {
                            "text": "Dorms build community",
                            "reasons": [
                                {
                                    "text": "Shared meals",
                                    "explanations": [{"type": "fact", "text": "Daily contact"}],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )

    mark_argument_summary_pending(session)
    session.refresh_from_db()

    assert session.argument_summary["status"] == "pending"
    assert session.argument_summary["speakers"][0]["claims"][0]["text"] == "Dorms build community"
    assert session.argument_summary["turn_count"] == session.turn_count


def test_speakers_from_summary_migrates_legacy_topic_claims() -> None:
    speakers = _speakers_from_summary(
        {
            "status": "ready",
            "claims": [
                {
                    "text": "AI helps learning",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Adaptive feedback"},
                            "explanations": [
                                {"type": "example", "text": "Personalized quizzes"},
                            ],
                        },
                    ],
                },
            ],
        },
    )

    assert len(speakers) == 1
    assert speakers[0]["claims"][0]["text"] == "AI helps learning"
    assert speakers[0]["claims"][0]["reasons"][0]["text"] == "Adaptive feedback"
    assert speakers[0]["claims"][0]["reasons"][0]["explanations"][0]["text"] == "Personalized quizzes"


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
def test_finalize_argument_summary_on_conclusion_schedules_only_when_concluded(user, monkeypatch) -> None:
    scheduled: list[int] = []

    def _capture(session: ConversationSession) -> None:
        scheduled.append(session.id)

    monkeypatch.setattr(
        "backend.conversation.services.argument_summary.schedule_argument_summary_for_session",
        _capture,
    )

    concluded = ConversationSession.objects.create(
        user=user,
        topic="Ended",
        turn_count=3,
        max_turns=25,
        terminate=True,
    )
    interrupted = ConversationSession.objects.create(
        user=user,
        topic="Interrupted",
        turn_count=3,
        max_turns=25,
        terminate=False,
    )

    finalize_argument_summary_on_conclusion(concluded)
    finalize_argument_summary_on_conclusion(interrupted)

    assert scheduled == [concluded.id]


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
                "claims": [
                    {
                        "text": "AI helps personalized learning",
                        "reasons": [],
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
    assert response.json()["speakers"][0]["claims"][0]["text"] == "AI helps personalized learning"


@pytest.mark.django_db
def test_user_question_at_turn_19_routes_to_agent_not_closing(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=19, max_turns=20)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", display_name="Jack", personality={"persona_name": "Discussion Driver"}),
        ],
    )
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="What do you all think about living on campus?",
        source="text",
    )

    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=18)

    assert decision.terminate is False
    assert decision.next_speaker_type == "agent"
    assert decision.reason == "user_question_answer"
