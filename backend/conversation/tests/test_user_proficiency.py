import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.user_proficiency import build_agent_proficiency_guidance
from backend.conversation.services.user_proficiency import longest_user_utterance_for_session
from backend.conversation.services.user_proficiency import resolve_user_proficiency
from backend.conversation.services.user_proficiency import update_proficiency_from_session


@pytest.mark.django_db
def test_build_agent_proficiency_guidance_uses_cefr_when_no_reference():
    guidance = build_agent_proficiency_guidance(cefr_level="b1", reference_utterance="")
    assert "Default proficiency: CEFR level B1" in guidance


@pytest.mark.django_db
def test_build_agent_proficiency_guidance_uses_reference_utterance():
    guidance = build_agent_proficiency_guidance(
        cefr_level="B1",
        reference_utterance="I think the policy is quite complicated for students.",
    )
    assert "Proficiency sample" in guidance
    assert "complicated for students" in guidance
    assert "CEFR" not in guidance


@pytest.mark.django_db
def test_longest_user_utterance_for_session(user):
    session = ConversationSession.objects.create(user=user, topic="climate")
    TurnRecord.objects.create(
        session=session,
        speaker="You",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Short.",
        turn_index=0,
    )
    TurnRecord.objects.create(
        session=session,
        speaker="You",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="This is my longest answer in the discussion.",
        turn_index=1,
    )
    assert longest_user_utterance_for_session(session) == "This is my longest answer in the discussion."


@pytest.mark.django_db
def test_resolve_user_proficiency_prefers_reference_utterance(user):
    user.userprofile.cefr_level = "C1"
    user.userprofile.proficiency_reference_utterance = "I think AI teachers could help some students."
    user.userprofile.save()

    proficiency = resolve_user_proficiency(user=user)

    assert proficiency["reference_utterance"] == "I think AI teachers could help some students."
    assert "Proficiency sample" in proficiency["proficiency_guidance"]
    assert "C1" not in proficiency["proficiency_guidance"]


@pytest.mark.django_db
def test_update_proficiency_from_session_saves_longest_utterance(user):
    session = ConversationSession.objects.create(user=user, topic="climate")
    TurnRecord.objects.create(
        session=session,
        speaker="You",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Short.",
        turn_index=0,
    )
    TurnRecord.objects.create(
        session=session,
        speaker="You",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="This is my longest answer in the discussion.",
        turn_index=1,
    )
    assert update_proficiency_from_session(session) is True
    user.userprofile.refresh_from_db()
    assert user.userprofile.proficiency_reference_utterance == "This is my longest answer in the discussion."
