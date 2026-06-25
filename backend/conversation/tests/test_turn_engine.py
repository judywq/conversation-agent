import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import process_agent_turn


@pytest.mark.django_db
def test_termination_when_max_turns_reached(user):
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=2, turn_count=2)
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.terminate is True


@pytest.mark.django_db
def test_forced_user_turn_has_priority(user):
    session = ConversationSession.objects.create(
        user=user,
        topic="t",
        pending_forced_user_turn=True,
        turn_count=1,
    )
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.terminate is False
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"


@pytest.mark.django_db
def test_append_turn_updates_session_state(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    processed = append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="hello",
        source="text",
    )
    session.refresh_from_db()
    assert processed.turn.turn_index == 0
    assert session.turn_count == 1
    assert session.previous_speaker == "user"


@pytest.mark.django_db
def test_pause_flag_persists(user):
    session = ConversationSession.objects.create(user=user, topic="t", paused=True)
    session.refresh_from_db()
    assert session.paused is True


@pytest.mark.django_db
def test_first_round_never_returns_makeshift(user):
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=0)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
            AgentProfile(session=session, agent_id="agent_3", personality={"persona_name": "Idea Explorer"}),
        ],
    )
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "agent"
    assert decision.next_speaker_id in {"agent_1", "agent_2", "agent_3"}
    assert decision.reason == "first_round_agent_open"


@pytest.mark.django_db
def test_weighted_balancing_routes_user_directly(user):
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=3)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
            AgentProfile(session=session, agent_id="agent_3", personality={"persona_name": "Idea Explorer"}),
        ],
    )
    append_turn(session, speaker="agent_1", speaker_type=TurnRecord.SPEAKER_TYPE_AGENT, utterance="a")
    append_turn(session, speaker="agent_2", speaker_type=TurnRecord.SPEAKER_TYPE_AGENT, utterance="b")
    append_turn(session, speaker="agent_3", speaker_type=TurnRecord.SPEAKER_TYPE_AGENT, utterance="c")

    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"
    assert decision.reason == "balanced_user_turn"


@pytest.mark.django_db
def test_weighted_balancing_selects_agent_with_biggest_deficit(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
            AgentProfile(session=session, agent_id="agent_3", personality={"persona_name": "Idea Explorer"}),
        ],
    )
    append_turn(session, speaker="user", speaker_type=TurnRecord.SPEAKER_TYPE_USER, utterance="u1")
    append_turn(session, speaker="user", speaker_type=TurnRecord.SPEAKER_TYPE_USER, utterance="u2")
    append_turn(session, speaker="agent_1", speaker_type=TurnRecord.SPEAKER_TYPE_AGENT, utterance="a1")

    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=1)
    assert decision.next_speaker_type == "agent"
    assert decision.next_speaker_id == "agent_3"


@pytest.mark.django_db
def test_last_turn_prefers_agent_wrap_up(user):
    """
    Regression: previously, at turn_count == max_turns - 1 the policy could still
    choose the user, leading to an immediate termination after the user spoke and
    no final agent wrap-up.
    """
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=19, max_turns=20)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
        ],
    )
    decision = decide_next_speaker(session, user_volunteered=True, last_user_turn_index=18)
    assert decision.terminate is False
    assert decision.next_speaker_type == "agent"
    assert decision.next_speaker_id in {"agent_1", "agent_2"}
    assert decision.reason == "closing_agent_turn"


@pytest.mark.django_db
def test_directive_target_agent_forces_next_speaker(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
            AgentProfile(session=session, agent_id="agent_3", personality={"persona_name": "Idea Explorer"}),
        ],
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Question for agent_2",
        metadata=None,
        source="text",
    )
    # Patch the stored metadata to simulate facilitator output for this test.
    session.turns.update(speech_act="DIRECTIVES", subtype="request_info", target="agent_2")
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "agent"
    assert decision.next_speaker_id == "agent_2"
    assert decision.reason == "directive_target_agent"


@pytest.mark.django_db
def test_directive_target_user_routes_directly(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"})
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Question for user",
        metadata=None,
        source="text",
    )
    session.turns.update(speech_act="DIRECTIVES", subtype="invite", target="user")
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"
    assert decision.reason == "directive_target_user"


@pytest.mark.django_db
def test_named_question_target_user_forces_user_next(user):
    user.name = "Judy"
    user.save()
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=2)
    AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        display_name="Jack",
        personality={"persona_name": "Discussion Driver"},
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="I think 10-15 hours is fine. Judy, what do you think?",
        metadata=None,
        source="text",
    )
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"
    assert decision.reason == "named_question_target_user"


@pytest.mark.django_db
def test_named_question_target_user_forces_user_next_when_period_ended(user):
    user.name = "Judy"
    user.save()
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=2)
    AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        display_name="Jack",
        personality={"persona_name": "Discussion Driver"},
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=(
            "Um, I take the school bus because it is easy and I can relax. "
            "Do you like taking the school bus, Judy."
        ),
        metadata=None,
        source="text",
    )
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"
    assert decision.reason == "named_question_target_user"


@pytest.mark.django_db
def test_agent_turn_name_target_fallback_routes_user_via_directive_metadata(user):
    user.name = "Judy"
    user.save()
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=1)
    AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        display_name="Jack",
        personality={"persona_name": "Discussion Driver"},
    )
    processed = process_agent_turn(
        session,
        speaker="agent_1",
        utterance="Do you like taking the school bus, Judy.",
        facilitator_plan={
            "type": "DIRECTIVES",
            "subtype": "request_info",
            "target": "everyone",
            "content_requirement": "Ask Judy about the school bus.",
            "retrieval_requirement": "none",
        },
        source="text",
    )
    assert processed.turn.target == "user"
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.next_speaker_type == "user"
    assert decision.next_speaker_id == "user"
    assert decision.reason == "directive_target_user"


@pytest.mark.django_db
def test_user_group_question_routes_to_agent_not_user(user):
    session = ConversationSession.objects.create(user=user, topic="Campus dorms", turn_count=2)
    AgentProfile.objects.bulk_create(
        [
            AgentProfile(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"}),
            AgentProfile(session=session, agent_id="agent_2", personality={"persona_name": "Fact Checker"}),
        ],
    )
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="What do you all think about living on campus?",
        source="text",
    )
    session.turns.update(target="everyone", speech_act="DIRECTIVES", subtype="request_info")

    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=1)

    assert decision.terminate is False
    assert decision.next_speaker_type == "agent"
    assert decision.next_speaker_id in {"agent_1", "agent_2"}
    assert decision.reason == "user_group_question"

