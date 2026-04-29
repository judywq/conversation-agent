import asyncio
import random

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.agent_selection import select_complementary_agent_personas
from backend.conversation.services.facilitator import build_facilitator_plan
from backend.conversation.services.agent import generate_agent_utterance
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import mark_terminate
from backend.conversation.services.turn_processor import process_agent_turn
from backend.conversation.services.turn_processor import process_user_turn
from backend.conversation.services.turn_processor import set_pending_forced_user_turn
from backend.conversation.services.turn_processor import set_user_override_requested
from backend.conversation.services.tts import synthesize_speech
from backend.conversation.services.names import pick_unique_names

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def select_agent_personas_for_session(ocean: dict[str, str], *, count: int = 3):
    selected = select_complementary_agent_personas(ocean, count=count)
    if len(selected) < count:
        msg = "backend/conversation/data/prompts/ must provide at least three agent personas"
        raise ValueError(msg)
    random.shuffle(selected)
    return selected


def next_higher_cefr_level(user_level: str | None) -> str:
    normalized = str(user_level or "").upper().strip()
    if normalized not in CEFR_LEVELS:
        return "B2"
    idx = CEFR_LEVELS.index(normalized)
    if idx >= len(CEFR_LEVELS) - 1:
        return CEFR_LEVELS[-1]
    return CEFR_LEVELS[idx + 1]


class ConversationConsumer(AsyncJsonWebsocketConsumer):
    """
    Authenticated WebSocket consumer with a minimal turn-engine implementation.

    This will be upgraded in later todos to use a real facilitator + agent generation,
    plus STT/TTS.
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_authenticated", False) is not True:
            await self.close(code=4401)
            return

        await self.accept()
        self.session_id: int | None = None
        self.user_volunteered: bool = False
        self.first_turn_choice: bool | None = None
        self._loop_task: asyncio.Task | None = None
        await self.send_json(
            {
                "type": "connected",
                "user_id": user.pk,
            },
        )

    def _ensure_advance_loop_running(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return

        async def runner():
            await self._advance_loop()

        task = asyncio.create_task(runner())
        self._loop_task = task

        def _clear(_t: asyncio.Task) -> None:
            if self._loop_task is _t:
                self._loop_task = None

        task.add_done_callback(_clear)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")

        if msg_type == "start_session":
            topic = str(content.get("topic") or "")
            if not topic.strip():
                await self.send_json({"type": "error", "message": "Enter a discussion topic before starting."})
                return
            profile_gate = await self._get_profile_gate_state()
            if profile_gate["profile_completed"] is not True:
                await self.send_json({"type": "error", "message": "Complete your profile before starting a conversation."})
                return
            if str(profile_gate["cefr_sample_topic"] or "").strip() != topic.strip():
                await self.send_json({"type": "error", "message": "Choose a CEFR listening level for this topic before starting."})
                return
            session = await self._create_session(topic=topic)
            self.session_id = session.id
            await self.send_json(
                {
                    "type": "session_started",
                    "session_id": session.id,
                    "topic": session.topic,
                },
            )
            await self.send_json({"type": "participants", "participants": await self._participants_payload(session.id)})
            # First-turn logic: ask whether the user wants to speak first.
            self.first_turn_choice = None
            await self.send_json({"type": "need_first_turn_choice"})
            return

        if msg_type == "first_turn_choice":
            if self.session_id is None:
                await self.send_json({"type": "error", "message": "No active session"})
                return
            speak_first = bool(content.get("speak_first"))
            self.first_turn_choice = speak_first
            if speak_first:
                await self.send_json({"type": "need_user_turn", "reason": "first_turn_user"})
                return
            self._ensure_advance_loop_running()
            return

        if msg_type in ("volunteer", "raise_hand"):
            # Treat "volunteer" as a raise-hand override signal.
            if self.session_id is None:
                await self.send_json({"type": "error", "message": "No active session"})
                return
            await self._set_user_override_requested(self.session_id, requested=True)
            await self.send_json({"type": "user_volunteered"})
            self._ensure_advance_loop_running()
            return

        if msg_type == "end_session":
            if self.session_id is not None:
                await self._mark_terminate(self.session_id)
            if self._loop_task is not None and not self._loop_task.done():
                self._loop_task.cancel()
            await self.send_json({"type": "session_ended"})
            return

        if msg_type == "pause":
            if self.session_id is None:
                await self.send_json({"type": "error", "message": "No active session"})
                return
            await self._set_paused(self.session_id, paused=True)
            await self.send_json({"type": "paused"})
            return

        if msg_type == "resume":
            if self.session_id is None:
                await self.send_json({"type": "error", "message": "No active session"})
                return
            await self._set_paused(self.session_id, paused=False)
            await self.send_json({"type": "resumed"})
            self._ensure_advance_loop_running()
            return

        if msg_type == "user_turn":
            if self.session_id is None:
                await self.send_json({"type": "error", "message": "No active session"})
                return

            utterance = str(content.get("utterance") or "").strip()
            if not utterance:
                await self.send_json({"type": "error", "message": "Empty utterance"})
                return

            source = str(content.get("source") or "text")
            _au = content.get("audio_url")
            if _au is None:
                audio_url = None
            else:
                s = str(_au).strip()
                audio_url = s or None
            await self._append_user_turn(
                self.session_id,
                utterance=utterance,
                source=source,
                audio_url=audio_url,
            )
            self._ensure_advance_loop_running()
            return

        await self.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    async def _advance_loop(self):
        """
        Advances the conversation by generating the next non-user turns (agent).
        If a user turn is needed, it will emit a `need_user_turn` event and stop.
        """
        if self.session_id is None:
            return

        # If we haven't resolved first-turn choice yet, block the engine.
        if self.first_turn_choice is None:
            return

        while True:
            session = await self._get_session(self.session_id)
            if session is None:
                return
            if session.paused:
                await self.send_json({"type": "paused"})
                return
            if session.terminate:
                await self.send_json({"type": "terminated", "reason": "terminate_flag"})
                return

            last_user_turn_index = await self._last_user_turn_index(session.id)
            decision = await database_sync_to_async(decide_next_speaker)(
                session,
                user_volunteered=self.user_volunteered,
                last_user_turn_index=last_user_turn_index,
            )

            if decision.terminate:
                await self.send_json({"type": "terminated", "reason": decision.reason})
                return

            assert decision.next_speaker_type is not None
            if decision.next_speaker_type == "user":
                self.user_volunteered = False
                if not session.pending_forced_user_turn:
                    await self._set_pending_forced_user_turn(session.id, pending=True)
                # Clear any raise-hand override once we've handed the floor to the user.
                await self._set_user_override_requested(session.id, requested=False)
                await self.send_json({"type": "need_user_turn", "reason": decision.reason})
                return

            if decision.next_speaker_type == "agent":
                await self.send_json({"type": "agent_status", "status": "thinking"})
                turn = await self._append_agent_llm_turn(session.id, agent_id=decision.next_speaker_id)
                session_after = await self._get_session(self.session_id)
                if session_after is None or session_after.paused or session_after.terminate:
                    return
                await self.send_json({"type": "turn", "turn": await self._turn_to_dict(turn)})
                await self.send_json({"type": "agent_status", "status": "finished"})
                continue

    @database_sync_to_async
    def _create_session(self, *, topic: str) -> ConversationSession:
        user = self.scope["user"]
        session = ConversationSession.objects.create(user=user, topic=topic)
        ocean = user.userprofile.ocean if hasattr(user, "userprofile") else {}
        user_cefr_level = user.userprofile.cefr_level if hasattr(user, "userprofile") else ""
        # Agents should match the user's selected level (no longer forced higher).
        agent_cefr_level = str(user_cefr_level or "").upper().strip() or "B2"
        selected_prompts = select_agent_personas_for_session(ocean, count=3)
        display_names = pick_unique_names(len(selected_prompts))
        leadership_by_slot = [0.8, 0.4, 0.6]
        AgentProfile.objects.bulk_create(
            [
                AgentProfile(
                    session=session,
                    agent_id=f"agent_{idx + 1}",
                    display_name=display_names[idx],
                    personality={
                        "persona_name": selected.prompt.persona_name,
                        "source_trait": selected.source_trait,
                        "user_level": selected.user_level,
                    },
                    traits={
                        "style": selected.prompt.persona_name.lower().replace(" ", "_"),
                        "leadership": leadership_by_slot[idx],
                        "proficiency_level": agent_cefr_level,
                        "complementary_score": selected.complementary_score,
                    },
                )
                for idx, selected in enumerate(selected_prompts)
            ],
        )
        return session

    @database_sync_to_async
    def _get_profile_gate_state(self) -> dict:
        user = self.scope["user"]
        if not getattr(user, "is_authenticated", False):
            return {"profile_completed": False, "cefr_sample_topic": ""}
        user_model = get_user_model()
        user = user_model.objects.select_related("userprofile").get(pk=user.pk)
        profile = getattr(user, "userprofile", None)
        if profile is None:
            return {"profile_completed": False, "cefr_sample_topic": ""}
        return {
            "profile_completed": bool(profile.profile_completed),
            "cefr_sample_topic": profile.cefr_sample_topic,
        }

    @database_sync_to_async
    def _get_session(self, session_id: int) -> ConversationSession | None:
        user = self.scope["user"]
        return ConversationSession.objects.filter(id=session_id, user=user).first()

    @database_sync_to_async
    def _participants_payload(self, session_id: int) -> list[dict]:
        session = (
            ConversationSession.objects.filter(id=session_id)
            .select_related("user__userprofile")
            .prefetch_related("agent_profiles")
            .first()
        )
        if session is None:
            return []

        profile = getattr(session.user, "userprofile", None)
        preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
        user_name = preferred or (getattr(session.user, "name", "") or "").strip() or "You"

        participants: list[dict] = [{"id": "user", "name": user_name, "type": "user"}]
        for a in session.agent_profiles.order_by("agent_id"):
            participants.append(
                {
                    "id": a.agent_id,
                    "name": a.display_name or a.agent_id,
                    "type": "agent",
                    "persona_name": (a.personality or {}).get("persona_name") or "",
                },
            )
        return participants

    @database_sync_to_async
    def _mark_terminate(self, session_id: int) -> None:
        session = ConversationSession.objects.get(id=session_id)
        mark_terminate(session)

    @database_sync_to_async
    def _set_paused(self, session_id: int, *, paused: bool) -> None:
        session = ConversationSession.objects.get(id=session_id)
        session.paused = paused
        session.save(update_fields=["paused", "updated_at"])

    @database_sync_to_async
    def _append_user_turn(
        self,
        session_id: int,
        *,
        utterance: str,
        source: str,
        audio_url: str | None = None,
    ) -> TurnRecord:
        session = ConversationSession.objects.get(id=session_id)
        processed = process_user_turn(
            session,
            utterance,
            source=source,
            audio_url=audio_url,
        )
        # Once the user has spoken, clear any "forced user" + override flags.
        if processed.session.pending_forced_user_turn:
            set_pending_forced_user_turn(processed.session, pending=False)
        set_user_override_requested(processed.session, requested=False)
        return processed.turn

    @database_sync_to_async
    def _append_agent_llm_turn(self, session_id: int, *, agent_id: str | None = None) -> TurnRecord:
        session = ConversationSession.objects.get(id=session_id)
        if agent_id:
            agent = AgentProfile.objects.get(session=session, agent_id=agent_id)
        elif session.turn_count == 0:
            # First agent turn (when user didn't speak first): pick highest leadership.
            agents = list(AgentProfile.objects.filter(session=session))
            agent = max(agents, key=lambda a: float(a.traits.get("leadership", 0.0)))
        else:
            idx = (session.turn_count % 3) + 1
            agent_id = f"agent_{idx}"
            agent = AgentProfile.objects.get(session=session, agent_id=agent_id)
        agent_id = agent.agent_id

        plan = build_facilitator_plan(session, agent=agent)
        utterance = generate_agent_utterance(session, agent=agent, facilitator_plan=plan)
        audio_url = None
        try:
            voice = agent.voice or "alloy"
            audio_url = synthesize_speech(text=utterance, voice=voice)
        except Exception:
            # If TTS fails (missing key, etc.), continue without audio.
            audio_url = None

        processed = process_agent_turn(
            session,
            speaker=agent_id,
            utterance=utterance,
            facilitator_plan=plan,
            source="llm",
            audio_url=audio_url,
        )
        return processed.turn

    @database_sync_to_async
    def _set_pending_forced_user_turn(self, session_id: int, *, pending: bool) -> None:
        session = ConversationSession.objects.get(id=session_id)
        set_pending_forced_user_turn(session, pending=pending)

    @database_sync_to_async
    def _set_user_override_requested(self, session_id: int, *, requested: bool) -> None:
        session = ConversationSession.objects.get(id=session_id)
        set_user_override_requested(session, requested=requested)

    @database_sync_to_async
    def _last_user_turn_index(self, session_id: int) -> int | None:
        last = (
            TurnRecord.objects.filter(session_id=session_id, speaker_type=TurnRecord.SPEAKER_TYPE_USER)
            .order_by("-turn_index")
            .first()
        )
        return last.turn_index if last else None

    @database_sync_to_async
    def _turn_to_dict(self, turn: TurnRecord) -> dict:
        # This runs in a sync thread so it's safe to query related objects.
        speaker_display_name = (turn.speaker or "").strip()
        if turn.speaker_type in (TurnRecord.SPEAKER_TYPE_AGENT, TurnRecord.SPEAKER_TYPE_MAKESHIFT):
            agent = AgentProfile.objects.filter(session_id=turn.session_id, agent_id=turn.speaker).first()
            speaker_display_name = (agent.display_name if agent and agent.display_name else turn.speaker).strip()
        elif turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
            session = ConversationSession.objects.filter(id=turn.session_id).select_related("user__userprofile").first()
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
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        }

