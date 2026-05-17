from unittest.mock import patch

import pytest
from django.conf import settings
from langchain_core.messages import AIMessage

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import UserMemory
from backend.conversation.services.user_memory_extraction import MemoryCandidate
from backend.conversation.services.user_memory_extraction import (
    extract_memory_candidates,
)
from backend.conversation.services.user_memory_extraction import parse_memory_response
from backend.conversation.services.user_memory_extraction import (
    persist_memory_candidates,
)
from backend.conversation.services.user_memory_extraction import (
    run_memory_extraction_for_turn,
)
from backend.conversation.services.user_memory_extraction import (
    schedule_memory_extraction_for_turn,
)
from backend.conversation.services.user_memory_extraction import validate_candidate


class FakeMemoryLLM:
    def __init__(self, content):
        self.content = content
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.content)


def test_user_memory_extraction_flag_exists():
    assert hasattr(settings, "USER_MEMORY_EXTRACTION_ENABLED")


def test_validate_candidate_accepts_learning_preference():
    candidate = MemoryCandidate(
        action="create",
        memory_type="learning_preference",
        content="The user prefers examples before grammar explanations.",
        confidence=0.9,
        source_label="conversation",
        reason="User explicitly stated a stable learning preference",
    )

    result = validate_candidate(candidate)

    assert result.accepted is True
    assert result.reason == "accepted"


@pytest.mark.parametrize("memory_type", ["", "random", "system_prompt"])
def test_validate_candidate_rejects_invalid_memory_type(memory_type):
    candidate = MemoryCandidate(
        action="create",
        memory_type=memory_type,
        content="The user prefers explanations in Chinese.",
        confidence=0.9,
        source_label="conversation",
        reason="test",
    )

    result = validate_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "invalid_memory_type"


@pytest.mark.parametrize("content", ["", "   ", "x" * 2001])
def test_validate_candidate_rejects_invalid_content(content):
    candidate = MemoryCandidate(
        action="create",
        memory_type="learning_preference",
        content=content,
        confidence=0.9,
        source_label="conversation",
        reason="test",
    )

    result = validate_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "invalid_content"


@pytest.mark.parametrize("confidence", [-0.1, 0.0, 0.49, 1.1])
def test_validate_candidate_rejects_invalid_or_low_confidence(confidence):
    candidate = MemoryCandidate(
        action="create",
        memory_type="learning_preference",
        content="The user prefers explanations in Chinese.",
        confidence=confidence,
        source_label="conversation",
        reason="test",
    )

    result = validate_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "low_confidence"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("我的密码是 abc123456", "sensitive"),
        ("my api key is sk-test-123", "sensitive"),
        ("请记住我的电话 13812345678", "sensitive"),
        ("我的邮箱是 test@example.com", "sensitive"),
        ("这次 topic 是学习汉语", "temporary"),
        ("The current topic is learning Chinese.", "temporary"),
        ("A1 sample: I like apples.", "cefr_sample"),
    ],
)
def test_validate_candidate_filters_sensitive_and_temporary_content(content, reason):
    candidate = MemoryCandidate(
        action="create",
        memory_type="profile",
        content=content,
        confidence=0.9,
        source_label="conversation",
        reason="test",
    )

    result = validate_candidate(candidate)

    assert result.accepted is False
    assert result.reason == reason


def test_validate_candidate_rejects_single_language_mistake_as_weakness():
    candidate = MemoryCandidate(
        action="create",
        memory_type="weakness",
        content="The user missed an article once in this turn.",
        confidence=0.9,
        source_label="conversation",
        reason="single mistake",
    )

    result = validate_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "weakness_insufficient_evidence"


def test_validate_candidate_accepts_explicit_weakness():
    candidate = MemoryCandidate(
        action="create",
        memory_type="weakness",
        content="The user explicitly struggles with English articles long term.",
        confidence=0.9,
        source_label="conversation",
        reason="explicit long-term weakness",
    )

    result = validate_candidate(candidate)

    assert result.accepted is True


def test_parse_memory_response_handles_valid_json():
    candidates = parse_memory_response(
        '{"memories":[{"action":"create","memory_type":"learning_preference",'
        '"content":"The user prefers explanations in Chinese.",'
        '"confidence":0.9,"reason":"explicit"}]}',
    )

    assert len(candidates) == 1
    assert candidates[0].memory_type == "learning_preference"


def test_parse_memory_response_handles_malformed_json():
    assert parse_memory_response("not json") == []


@pytest.mark.django_db
def test_extract_memory_candidates_uses_llm(user):
    session = ConversationSession.objects.create(user=user, topic="English speaking")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Please explain grammar in Chinese from now on.",
        turn_index=0,
    )
    llm = FakeMemoryLLM(
        '{"memories":[{"action":"create","memory_type":"instruction",'
        '"content":"The user wants grammar explained in Chinese.",'
        '"confidence":0.9,"reason":"explicit"}]}',
    )

    candidates = extract_memory_candidates(
        user=user,
        session=session,
        turn=turn,
        llm=llm,
    )

    assert len(candidates) == 1
    assert candidates[0].memory_type == "instruction"
    assert "Please explain grammar in Chinese" in str(llm.messages[0].content)
    assert "Write every content and reason field in English" in str(llm.messages[0].content)


@pytest.mark.django_db
def test_persist_memory_candidates_creates_user_memory(user):
    session = ConversationSession.objects.create(user=user, topic="English")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Please explain grammar in Chinese from now on.",
        turn_index=0,
    )
    candidate = MemoryCandidate(
        action="create",
        memory_type="instruction",
        content="The user wants grammar explained in Chinese.",
        confidence=0.9,
        source_label="conversation",
        reason="explicit",
    )

    result = persist_memory_candidates(
        user=user,
        session=session,
        turn=turn,
        candidates=[candidate],
    )

    assert result.created_count == 1
    memory = UserMemory.objects.get(user=user)
    assert memory.memory_type == "instruction"
    assert memory.source_label == "conversation_extraction"
    assert memory.metadata["session_id"] == session.id
    assert memory.metadata["turn_id"] == turn.id
    assert memory.embedding is None


@pytest.mark.django_db
def test_persist_memory_candidates_skips_exact_duplicate(user):
    session = ConversationSession.objects.create(user=user, topic="English")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Please explain grammar in Chinese from now on.",
        turn_index=0,
    )
    UserMemory.objects.create(
        user=user,
        memory_type="instruction",
        content="The user wants grammar explained in Chinese.",
        source_label="conversation_extraction",
    )
    candidate = MemoryCandidate(
        action="create",
        memory_type="instruction",
        content=" The user wants grammar explained in Chinese. ",
        confidence=0.9,
        source_label="conversation",
        reason="explicit",
    )

    result = persist_memory_candidates(
        user=user,
        session=session,
        turn=turn,
        candidates=[candidate],
    )

    assert result.created_count == 0
    assert result.skipped_count == 1
    assert UserMemory.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_run_memory_extraction_for_turn_handles_missing_records(user):
    run_memory_extraction_for_turn(user_id=user.id, session_id=999999, turn_id=999999)


@pytest.mark.django_db
def test_schedule_memory_extraction_for_turn_submits_scalar_ids(
    settings,
    user,
    django_capture_on_commit_callbacks,
):
    settings.USER_MEMORY_EXTRACTION_ENABLED = True
    session = ConversationSession.objects.create(user=user, topic="English")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Please explain grammar in Chinese from now on.",
        turn_index=0,
    )

    with (
        patch(
            "backend.conversation.services.user_memory_extraction._submit_background",
        ) as submit,
        django_capture_on_commit_callbacks(execute=True),
    ):
        schedule_memory_extraction_for_turn(turn)

    assert submit.call_count == 1
    args = submit.call_args.args
    kwargs = submit.call_args.kwargs
    assert args[0] is run_memory_extraction_for_turn
    assert kwargs == {"user_id": user.id, "session_id": session.id, "turn_id": turn.id}


@pytest.mark.django_db
def test_schedule_memory_extraction_for_turn_respects_flag(
    settings,
    user,
    django_capture_on_commit_callbacks,
):
    settings.USER_MEMORY_EXTRACTION_ENABLED = False
    session = ConversationSession.objects.create(user=user, topic="English")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="hello",
        turn_index=0,
    )

    with (
        patch(
            "backend.conversation.services.user_memory_extraction._submit_background",
        ) as submit,
        django_capture_on_commit_callbacks(execute=True),
    ):
        schedule_memory_extraction_for_turn(turn)

    submit.assert_not_called()


@pytest.mark.django_db
def test_user_turn_signal_schedules_memory_extraction(settings, user):
    settings.USER_MEMORY_EXTRACTION_ENABLED = True
    session = ConversationSession.objects.create(user=user, topic="English")

    with patch(
        "backend.conversation.user_memory_signals.schedule_memory_extraction_for_turn",
    ) as schedule:
        turn = TurnRecord.objects.create(
            session=session,
            speaker="user",
            speaker_type=TurnRecord.SPEAKER_TYPE_USER,
            utterance="Please explain grammar in Chinese from now on.",
            turn_index=0,
        )

    schedule.assert_called_once_with(turn)


@pytest.mark.django_db
def test_agent_turn_signal_does_not_schedule_memory_extraction(settings, user):
    settings.USER_MEMORY_EXTRACTION_ENABLED = True
    session = ConversationSession.objects.create(user=user, topic="English")

    with patch(
        "backend.conversation.user_memory_signals.schedule_memory_extraction_for_turn",
    ) as schedule:
        TurnRecord.objects.create(
            session=session,
            speaker="agent_1",
            speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
            utterance="hello",
            turn_index=0,
        )

    schedule.assert_not_called()
