import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.facilitator import apply_experience_plan_nudge
from backend.conversation.services.facilitator import apply_user_question_answer_plan
from backend.conversation.services.facilitator import detect_anecdote_opportunity
from backend.conversation.services.facilitator import finalize_facilitator_plan
from backend.conversation.services.facilitator import is_user_group_question_turn
from backend.conversation.services.turn_processor import append_turn


@pytest.mark.django_db
def test_detect_anecdote_opportunity_when_user_invites_sharing(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Campus dorms", turn_count=1)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Have you ever lived in a dorm? What was your experience?",
        source="text",
    )
    session.turns.update(target="everyone")

    assert detect_anecdote_opportunity(session) is True


@pytest.mark.django_db
def test_apply_experience_plan_nudge_sets_personal_experience(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Campus clubs", turn_count=2)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Anyone else have a club story to share?",
        source="text",
    )

    plan = apply_experience_plan_nudge(
        session,
        {"type": "ASSERTIVES", "subtype": "inform", "content_requirement": "Add a factual point."},
        is_beginning=False,
        is_ending=False,
        is_winding_down=False,
    )

    assert plan["personal_experience"] is True
    assert plan["retrieval_requirement"] == "memory"
    assert plan["subtype"] == "opinion"


@pytest.mark.django_db
def test_apply_user_question_answer_plan_targets_user(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Study habits", turn_count=2)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="What do you all think about studying in the library?",
        source="text",
    )
    session.turns.update(target="everyone", speech_act="DIRECTIVES", subtype="request_info")

    plan = apply_user_question_answer_plan(
        session,
        {"type": "ASSERTIVES", "subtype": "inform", "content_requirement": "Share a fact."},
        is_ending=False,
        is_winding_down=False,
    )

    assert plan["target"] == "user"
    assert "answer" in plan["content_requirement"].casefold()


@pytest.mark.django_db
def test_finalize_facilitator_plan_prefers_user_question_over_anecdote(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Campus life", turn_count=2)
    AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        display_name="Alex",
        personality={"persona_name": "Discussion Driver"},
    )
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Have you ever joined a club? What do you all think?",
        source="text",
    )
    session.turns.update(target="everyone")

    plan = finalize_facilitator_plan(
        session,
        {
            "type": "ASSERTIVES",
            "subtype": "inform",
            "content_requirement": "Share a factual point.",
            "retrieval_requirement": "none",
            "personal_experience": False,
        },
        is_beginning=False,
        is_ending=False,
        is_winding_down=False,
    )

    assert plan["target"] == "user"
    assert plan["personal_experience"] is False


def test_is_user_group_question_turn_true_for_everyone_question() -> None:
    turn = TurnRecord(
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="What do you all think about online classes?",
        target="everyone",
    )
    assert is_user_group_question_turn(turn) is True
