from __future__ import annotations

import re

from django.conf import settings
from django.db import models

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord

_INTERROGATIVE_START = re.compile(
    r"^(?:do|does|did|can|could|would|will|what|how|why|where|when|who|"
    r"is|are|was|were|have|has|had)\b",
    re.IGNORECASE,
)

_CLOSING_SUBTYPES = frozenset({"close_session", "thank"})
_CLOSING_SPEECH_ACTS = frozenset({"DECLARATIONS", "EXPRESSIVES"})
_USER_CLOSE_REQUEST_SUBTYPE = "request_closing"
_CLOSING_PHRASES = (
    "thanks everyone",
    "thank you everyone",
    "great chat",
    "good talk",
    "see you",
    "bye everyone",
)


def last_real_turn(session: ConversationSession) -> TurnRecord | None:
    return (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")
        .first()
    )


def is_interrogative_utterance(text: str) -> bool:
    utterance = (text or "").strip()
    if not utterance:
        return False
    if utterance.endswith("?"):
        return True
    parts = re.split(r"(?<=[.!?])\s+", utterance)
    parts = [part.strip() for part in parts if part.strip()]
    last = parts[-1] if parts else utterance
    core = last.rstrip(".!?").strip()
    return bool(core and _INTERROGATIVE_START.match(core))


def max_extension_turns() -> int:
    return int(getattr(settings, "CONVERSATION_MAX_EXTENSION_TURNS", 4) or 4)


def is_past_max_turns(session: ConversationSession) -> bool:
    return int(session.turn_count) >= int(session.max_turns)


def is_winding_down_turn(session: ConversationSession) -> bool:
    next_turn_count = int(session.turn_count) + 1
    return next_turn_count == int(session.max_turns) and next_turn_count > 1


def is_hard_cap_reached(session: ConversationSession) -> bool:
    return int(session.turn_count) >= int(session.max_turns) + max_extension_turns()


def user_turns_allowed(session: ConversationSession) -> bool:
    if user_close_pending(session):
        return False
    return int(session.turn_count) < int(session.max_turns)


def last_user_question_turn(session: ConversationSession) -> TurnRecord | None:
    last = last_real_turn(session)
    if last is None or last.speaker_type != TurnRecord.SPEAKER_TYPE_USER:
        return None
    if not is_interrogative_utterance(last.utterance):
        return None
    return last


def has_unanswered_user_question(session: ConversationSession) -> bool:
    return last_user_question_turn(session) is not None


def last_user_close_request_turn(session: ConversationSession) -> TurnRecord | None:
    return (
        TurnRecord.objects.filter(
            session=session,
            speaker_type=TurnRecord.SPEAKER_TYPE_USER,
            speech_act="DIRECTIVES",
            subtype=_USER_CLOSE_REQUEST_SUBTYPE,
        )
        .order_by("-turn_index", "-subturn_index")
        .first()
    )


def _is_qualifying_closing_turn(turn: TurnRecord) -> bool:
    if turn.speaker_type != TurnRecord.SPEAKER_TYPE_AGENT:
        return False
    speech_act = str(turn.speech_act or "").upper()
    subtype = str(turn.subtype or "").strip().casefold()
    if speech_act in _CLOSING_SPEECH_ACTS and subtype in _CLOSING_SUBTYPES:
        return True
    utterance = (turn.utterance or "").casefold()
    return any(phrase in utterance for phrase in _CLOSING_PHRASES)


def user_close_pending(session: ConversationSession) -> bool:
    close_request = last_user_close_request_turn(session)
    if close_request is None:
        return False
    later_turns = (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .filter(
            models.Q(turn_index__gt=close_request.turn_index)
            | models.Q(
                turn_index=close_request.turn_index,
                subturn_index__gt=close_request.subturn_index,
            ),
        )
    )
    for turn in later_turns:
        if _is_qualifying_closing_turn(turn):
            return False
    return True


def closing_turn_delivered(session: ConversationSession) -> bool:
    last = last_real_turn(session)
    if last is None:
        return False
    return _is_qualifying_closing_turn(last)


def should_request_closing_agent(session: ConversationSession) -> bool:
    if user_close_pending(session):
        if has_unanswered_user_question(session):
            return False
        return True
    if not is_past_max_turns(session):
        return False
    if has_unanswered_user_question(session):
        return False
    return not closing_turn_delivered(session)


def is_closing_turn(session: ConversationSession) -> bool:
    return should_request_closing_agent(session)


def should_terminate(session: ConversationSession) -> bool:
    if session.terminate:
        return True
    if is_hard_cap_reached(session):
        return True
    if last_user_close_request_turn(session) is not None and not user_close_pending(session):
        return True
    if not is_past_max_turns(session):
        return False
    if has_unanswered_user_question(session):
        return False
    return closing_turn_delivered(session)
