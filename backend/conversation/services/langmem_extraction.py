from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.db import transaction

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.speaker_profiles import extract_and_update_profiles

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="langmem-extraction",
)


def langmem_extraction_enabled() -> bool:
    return bool(
        getattr(settings, "SPEAKER_PROFILES_ENABLED", True)
        and getattr(settings, "LANGMEM_ENABLED", True)
        and getattr(settings, "LANGMEM_PROFILE_EXTRACTION_ENABLED", True)
    )


def turns_to_langmem_messages(turns: list[TurnRecord]) -> list[dict[str, str]]:
    """Convert turns to LangMem messages with explicit speaker prefixes."""
    messages: list[dict[str, str]] = []
    for turn in turns:
        utterance = (turn.utterance or "").strip()
        if not utterance:
            continue
        if turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
            role = "user"
            speaker_tag = "user"
        else:
            role = "assistant"
            speaker_tag = (turn.speaker or "").strip() or "agent"
        messages.append(
            {
                "role": role,
                "content": f"[{speaker_tag}] {utterance}",
            },
        )
    return messages


def _submit_background(func: Any, **kwargs: Any) -> None:
    _EXECUTOR.submit(func, **kwargs)


def run_langmem_extraction_for_turn(
    *,
    user_id: int,
    session_id: int,
    turn_id: int,
) -> None:
    user_model = get_user_model()
    user = user_model.objects.filter(id=user_id).first()
    session = ConversationSession.objects.filter(id=session_id, user_id=user_id).first()
    turn = TurnRecord.objects.filter(id=turn_id, session_id=session_id).first()
    if user is None or session is None or turn is None:
        logger.info(
            "langmem_extraction_missing_records",
            extra={"user_id": user_id, "session_id": session_id, "turn_id": turn_id},
        )
        close_old_connections()
        return

    try:
        turns = get_short_term_turns(session, limit=10)
        messages = turns_to_langmem_messages(turns)
        if not messages:
            return

        if turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
            extract_and_update_profiles(user, messages)
        elif turn.speaker_type == TurnRecord.SPEAKER_TYPE_AGENT:
            agent_slug = (turn.speaker or "").strip()
            if not agent_slug:
                return
            extract_and_update_profiles(user, messages, agent_slug=agent_slug)
    except Exception:
        logger.exception(
            "langmem_extraction_failed",
            extra={"user_id": user_id, "session_id": session_id, "turn_id": turn_id},
        )
    finally:
        close_old_connections()


def schedule_langmem_extraction_for_turn(turn: TurnRecord) -> None:
    if not langmem_extraction_enabled():
        return
    if turn.speaker_type not in (
        TurnRecord.SPEAKER_TYPE_USER,
        TurnRecord.SPEAKER_TYPE_AGENT,
    ):
        return

    user_id = turn.session.user_id
    session_id = turn.session_id
    turn_id = turn.id

    transaction.on_commit(
        lambda: _submit_background(
            run_langmem_extraction_for_turn,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
        ),
    )
