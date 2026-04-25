import json
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.prompts import PROMPT_KEY_SPEECH_ACT_CLASSIFY
from backend.conversation.prompts import get_prompt_pair
from backend.conversation.services.facilitator import coerce_speech_act_plan
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages


@dataclass(frozen=True)
class ProcessedTurn:
    turn: TurnRecord
    session: ConversationSession


def _default_user_speech_act_plan() -> dict:
    return coerce_speech_act_plan({"type": "ASSERTIVES", "subtype": "opinion"})


def classify_user_speech_act(
    session: ConversationSession,
    utterance: str,
    *,
    source: str | None = None,
    audio_url: str | None = None,
) -> dict:
    """LLM classifies the user's latest utterance (transcript) into a speech-act plan shape."""
    turns = get_short_term_turns(session, limit=10)
    context = turns_to_messages(turns)
    pair = get_prompt_pair(PROMPT_KEY_SPEECH_ACT_CLASSIFY)
    system = SystemMessage(content=pair.system_template)
    human = HumanMessage(
        content=json.dumps(
            {
                "topic": session.topic,
                "utterance": utterance,
                "source": source,
                "audio_url": audio_url,
                "previous_speaker": session.previous_speaker,
                "recent_turns": context,
            },
            ensure_ascii=False,
        ),
    )
    llm = get_default_chat_llm()
    result = llm.invoke([system, human])
    raw = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _default_user_speech_act_plan()
    except json.JSONDecodeError:
        return _default_user_speech_act_plan()
    return coerce_speech_act_plan(parsed)


def append_user_turn_classified(
    session: ConversationSession,
    utterance: str,
    *,
    source: str | None = None,
    audio_url: str | None = None,
) -> ProcessedTurn:
    plan = classify_user_speech_act(
        session,
        utterance,
        source=source,
        audio_url=audio_url,
    )
    return append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance=utterance,
        speech_act=str(plan.get("type") or ""),
        subtype=plan.get("subtype"),
        target=plan.get("target"),
        source=source,
        audio_url=audio_url,
    )


def append_turn(
    session: ConversationSession,
    *,
    speaker: str,
    speaker_type: str,
    utterance: str,
    speech_act: str = "",
    subtype: str | None = None,
    target: str | None = None,
    source: str | None = None,
    audio_url: str | None = None,
) -> ProcessedTurn:
    turn = TurnRecord.objects.create(
        session=session,
        speaker=speaker,
        speaker_type=speaker_type,
        utterance=utterance,
        speech_act=speech_act,
        subtype=subtype,
        target=target,
        turn_index=session.turn_count,
        source=source,
        audio_url=audio_url,
    )

    # Update state
    session.turn_count += 1
    session.previous_speaker = speaker
    session.save(
        update_fields=[
            "turn_count",
            "previous_speaker",
            "updated_at",
        ],
    )

    return ProcessedTurn(turn=turn, session=session)


def set_pending_forced_user_turn(session: ConversationSession, *, pending: bool) -> ConversationSession:
    session.pending_forced_user_turn = pending
    session.save(update_fields=["pending_forced_user_turn", "updated_at"])
    return session


def set_user_override_requested(session: ConversationSession, *, requested: bool) -> ConversationSession:
    session.user_override_requested = requested
    session.save(update_fields=["user_override_requested", "updated_at"])
    return session


def mark_terminate(session: ConversationSession) -> ConversationSession:
    session.terminate = True
    session.save(update_fields=["terminate", "updated_at"])
    return session

