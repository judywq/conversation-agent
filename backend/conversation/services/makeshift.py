from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import set_pending_forced_user_turn


def invite_user(session: ConversationSession) -> TurnRecord:
    previous = session.previous_speaker or "Someone"
    utterance = f"{previous}: Would you like to share your thoughts next?"
    processed = append_turn(
        session,
        speaker=previous,
        speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT,
        utterance=utterance,
        speech_act="DIRECTIVES",
        subtype="invite",
        target="user",
        source="system",
    )
    set_pending_forced_user_turn(processed.session, pending=True)
    return processed.turn

