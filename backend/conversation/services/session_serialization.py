from __future__ import annotations

from typing import Any

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.argument_summary import get_argument_summary_for_session
from backend.conversation.services.conversation_phase import should_terminate


def can_continue_session(session: ConversationSession) -> bool:
    if session.terminate:
        return False
    if session.turn_count <= 0:
        return False
    return not should_terminate(session)


def turn_record_to_dict(*, turn: TurnRecord, session: ConversationSession | None = None) -> dict[str, Any]:
    speaker_display_name = (turn.speaker or "").strip()
    if turn.speaker_type in (TurnRecord.SPEAKER_TYPE_AGENT, TurnRecord.SPEAKER_TYPE_MAKESHIFT):
        agent = AgentProfile.objects.filter(session_id=turn.session_id, agent_id=turn.speaker).first()
        speaker_display_name = (agent.display_name if agent and agent.display_name else turn.speaker).strip()
    elif turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
        if session is None:
            session = (
                ConversationSession.objects.filter(id=turn.session_id)
                .select_related("user__userprofile")
                .first()
            )
        if session is not None:
            profile = getattr(session.user, "userprofile", None)
            preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
            if preferred:
                speaker_display_name = preferred
            else:
                name = (getattr(session.user, "name", "") or "").strip()
                speaker_display_name = name or "You"
        else:
            speaker_display_name = "You"

    return {
        "speaker": turn.speaker,
        "speaker_display_name": speaker_display_name,
        "speaker_type": turn.speaker_type,
        "utterance": turn.utterance,
        "speech_act": turn.speech_act,
        "subtype": turn.subtype,
        "target": turn.target,
        "turn_index": turn.turn_index,
        "subturn_index": getattr(turn, "subturn_index", 0),
        "source": turn.source,
        "audio_url": turn.audio_url,
        "lipsync": turn.lipsync,
        "created_at": turn.created_at.isoformat() if turn.created_at else None,
    }


def session_summary_to_dict(session: ConversationSession) -> dict[str, Any]:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    summary_status = stored.get("status") if stored else None
    return {
        "id": session.id,
        "topic": session.topic,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "terminate": session.terminate,
        "paused": session.paused,
        "news_category": session.news_category,
        "news_subtopic": session.news_subtopic,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "argument_summary_status": summary_status,
        "can_continue": can_continue_session(session),
    }


def session_detail_to_dict(session: ConversationSession) -> dict[str, Any]:
    payload = session_summary_to_dict(session)
    turns = list(session.turns.order_by("turn_index", "subturn_index", "id"))
    payload["turns"] = [turn_record_to_dict(turn=turn, session=session) for turn in turns]
    payload["argument_summary"] = get_argument_summary_for_session(session)
    return payload
