from dataclasses import dataclass

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord


@dataclass(frozen=True)
class ProcessedTurn:
    turn: TurnRecord
    session: ConversationSession


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


def mark_terminate(session: ConversationSession) -> ConversationSession:
    session.terminate = True
    session.save(update_fields=["terminate", "updated_at"])
    return session

