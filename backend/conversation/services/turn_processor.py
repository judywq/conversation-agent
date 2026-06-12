import json
from dataclasses import dataclass

from django.db import models
from langchain_core.messages import SystemMessage

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.prompts import load_speech_act_classifier_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.facilitator import ALLOWED_SA
from backend.conversation.services.facilitator import ALLOWED_TAXONOMY
from backend.conversation.services.facilitator import coerce_speech_act_plan
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages


@dataclass(frozen=True)
class ProcessedTurn:
    turn: TurnRecord
    session: ConversationSession


@dataclass(frozen=True)
class TurnMetadata:
    type: str
    subtype: str | None
    target: str | None
    content_requirement: str
    retrieval_requirement: str


def _default_user_speech_act_plan() -> dict:
    return coerce_speech_act_plan({"type": "ASSERTIVES", "subtype": "opinion"})


def _choose_classifier_item(parsed: object, *, utterance: str) -> dict:
    if isinstance(parsed, dict):
        return parsed
    if not isinstance(parsed, list):
        return {}

    normalized_utterance = utterance.strip().casefold()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        sentence = str(item.get("sentence") or "").strip().casefold()
        if sentence and sentence == normalized_utterance:
            return item

    for item in parsed:
        if isinstance(item, dict):
            return item
    return {}


def classify_user_speech_act(
    session: ConversationSession,
    utterance: str,
    *,
    source: str | None = None,
    audio_url: str | None = None,
) -> dict:
    """LLM classifies the user's latest utterance (transcript) into a speech-act plan shape."""
    turns = get_short_term_turns(session, limit=3)
    context = turns_to_messages(turns)
    speech_act_options = ALLOWED_TAXONOMY
    template = load_speech_act_classifier_prompt()
    participants = _participants_name_map(session)
    prompt_text = render_prompt_template(
        template,
        utterance=utterance,
        participants=json.dumps(participants, ensure_ascii=False),
        history=json.dumps(context, ensure_ascii=False, indent=2),
        speech_act_options=json.dumps(speech_act_options, ensure_ascii=False),
    )
    system = SystemMessage(content=prompt_text)
    llm = get_default_chat_llm()
    result = llm.invoke([system])
    raw = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = _choose_classifier_item(json.loads(raw), utterance=utterance)
        if not parsed:
            return _default_user_speech_act_plan()
    except json.JSONDecodeError:
        return _default_user_speech_act_plan()
    coerced = coerce_speech_act_plan(parsed)
    return _apply_name_target_fallback(session, utterance, coerced, participants)


def _participants_name_map(session: ConversationSession) -> dict[str, str]:
    # id -> display_name
    mapping: dict[str, str] = {"user": "user"}
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    user_name = preferred or (getattr(session.user, "name", "") or "").strip() or "You"
    mapping["user"] = user_name
    for a in session.agent_profiles.order_by("agent_id"):
        mapping[a.agent_id] = (a.display_name or a.agent_id).strip()
    return mapping


def _apply_name_target_fallback(
    session: ConversationSession,
    utterance: str,
    plan: dict,
    participants: dict[str, str],
) -> dict:
    # If DIRECTIVES but target is missing/too broad, detect a named participant in the utterance.
    if str(plan.get("type") or "").upper() != "DIRECTIVES":
        return plan
    target = plan.get("target")
    target = str(target).strip() if target is not None else ""
    if target and target.lower() not in {"everyone", "all", "null"}:
        return plan

    u = (utterance or "").casefold()
    # Prefer explicit "name," patterns first.
    for pid, display in participants.items():
        d = (display or "").strip()
        if not d:
            continue
        dc = d.casefold()
        if f"{dc}," in u or f"{dc}?" in u or f"{dc}." in u:
            plan["target"] = pid
            return plan
    # Fallback: any word-boundary match.
    for pid, display in participants.items():
        d = (display or "").strip()
        if not d:
            continue
        dc = d.casefold()
        if dc in u:
            plan["target"] = pid
            return plan
    return plan


_MAJOR_SA_TYPES = frozenset(ALLOWED_SA.keys())


def _normalize_speech_act_counters(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {"major": {}, "subtype": {"ASSERTIVES": {}, "DIRECTIVES": {}}}
    major = raw.get("major")
    if not isinstance(major, dict):
        major = {}
    subtype_root = raw.get("subtype")
    if not isinstance(subtype_root, dict):
        subtype_root = {}
    assertives_sub = subtype_root.get("ASSERTIVES")
    directives_sub = subtype_root.get("DIRECTIVES")
    if not isinstance(assertives_sub, dict):
        assertives_sub = {}
    if not isinstance(directives_sub, dict):
        directives_sub = {}
    return {
        "major": dict(major),
        "subtype": {"ASSERTIVES": dict(assertives_sub), "DIRECTIVES": dict(directives_sub)},
    }


def _increment_speech_act_counters(session: ConversationSession, metadata: TurnMetadata) -> None:
    sa_type = str(metadata.type or "").strip().upper()
    if not sa_type or sa_type not in _MAJOR_SA_TYPES:
        return
    counters = _normalize_speech_act_counters(session.speech_act_counters)
    major = counters["major"]
    assert isinstance(major, dict)
    major[sa_type] = int(major.get(sa_type, 0)) + 1

    if sa_type in ("ASSERTIVES", "DIRECTIVES"):
        st = metadata.subtype
        st_norm = str(st).strip().lower() if st is not None else ""
        if st_norm and st_norm in ALLOWED_SA.get(sa_type, set()):
            sub_map = counters["subtype"][sa_type]
            assert isinstance(sub_map, dict)
            sub_map[st_norm] = int(sub_map.get(st_norm, 0)) + 1

    session.speech_act_counters = counters


def metadata_from_plan(plan: dict) -> TurnMetadata:
    normalized = coerce_speech_act_plan(plan)
    return TurnMetadata(
        type=str(normalized.get("type") or ""),
        subtype=normalized.get("subtype"),
        target=normalized.get("target"),
        content_requirement=str(normalized.get("content_requirement") or ""),
        retrieval_requirement=str(normalized.get("retrieval_requirement") or ""),
    )


def process_user_turn(
    session: ConversationSession,
    utterance: str,
    *,
    source: str | None = None,
    audio_url: str | None = None,
) -> ProcessedTurn:
    metadata = metadata_from_plan(
        classify_user_speech_act(
            session,
            utterance,
            source=source,
            audio_url=audio_url,
        ),
    )
    return append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance=utterance,
        metadata=metadata,
        source=source,
        audio_url=audio_url,
    )


def process_agent_turn(
    session: ConversationSession,
    *,
    speaker: str,
    utterance: str,
    facilitator_plan: dict,
    source: str | None = None,
    audio_url: str | None = None,
    utterance_tts: str = "",
    lipsync: dict | None = None,
) -> ProcessedTurn:
    metadata = metadata_from_plan(facilitator_plan)
    return append_turn(
        session,
        speaker=speaker,
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=utterance,
        metadata=metadata,
        source=source,
        audio_url=audio_url,
        utterance_tts=utterance_tts,
        lipsync=lipsync,
    )


def append_turn(
    session: ConversationSession,
    *,
    speaker: str,
    speaker_type: str,
    utterance: str,
    metadata: TurnMetadata | None = None,
    source: str | None = None,
    audio_url: str | None = None,
    utterance_tts: str = "",
    lipsync: dict | None = None,
) -> ProcessedTurn:
    metadata = metadata or TurnMetadata(
        type="",
        subtype=None,
        target=None,
        content_requirement="",
        retrieval_requirement="",
    )
    if speaker_type == TurnRecord.SPEAKER_TYPE_MAKESHIFT:
        # Makeshift is an appendix to the previous "real" turn: do NOT increment turn_count,
        # and do NOT change previous_speaker. Store it as a sub-turn.
        base_turn_index = max(0, session.turn_count - 1)
        if session.turn_count <= 0 and not TurnRecord.objects.filter(session=session).exists():
            base_turn_index = 0
            subturn_index = 0
        else:
            existing_max = (
                TurnRecord.objects.filter(session=session, turn_index=base_turn_index).aggregate(
                    models.Max("subturn_index"),
                )["subturn_index__max"]
                or 0
            )
            subturn_index = int(existing_max) + 1
    else:
        base_turn_index = session.turn_count
        subturn_index = 0

    turn = TurnRecord.objects.create(
        session=session,
        speaker=speaker,
        speaker_type=speaker_type,
        utterance=utterance,
        utterance_tts=utterance_tts or "",
        speech_act=metadata.type,
        subtype=metadata.subtype,
        target=metadata.target,
        turn_index=base_turn_index,
        subturn_index=subturn_index,
        source=source,
        audio_url=audio_url,
        lipsync=lipsync,
    )

    _increment_speech_act_counters(session, metadata)

    # Update state (but makeshift doesn't count as a separate turn)
    if speaker_type != TurnRecord.SPEAKER_TYPE_MAKESHIFT:
        session.turn_count += 1
        session.previous_speaker = speaker
        session.save(
            update_fields=[
                "turn_count",
                "previous_speaker",
                "speech_act_counters",
                "updated_at",
            ],
        )
    else:
        session.save(update_fields=["speech_act_counters", "updated_at"])

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

