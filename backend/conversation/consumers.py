import asyncio
import logging
import random
import time
from uuid import uuid4

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnEngineLog
from backend.conversation.models import TurnRecord
from backend.conversation.services.agent import generate_agent_utterance_with_retrieval
from backend.conversation.services.agent import resolve_agent_retrieval_sources
from backend.conversation.services.cefr_levels import normalize_user_cefr_level
from backend.conversation.services.session_news_chunks import materialize_session_news_knowledge
from backend.conversation.services.session_news_chunks import materialize_session_web_knowledge
from backend.conversation.services.agent_selection import (
    select_complementary_agent_personas,
)
from backend.conversation.services.facilitator import build_facilitator_plan
from backend.conversation.services.names import pick_voice_preset_for_persona
from backend.conversation.services.names import provider_voice_id
from backend.conversation.services.retrieval import persist_turn_retrieval_safely
from backend.conversation.services.tts import synthesize_speech_with_lipsync
from backend.conversation.services.tts import tts_provider_timeouts
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import mark_terminate
from backend.conversation.services.turn_processor import process_agent_turn
from backend.conversation.services.turn_processor import process_user_turn
from backend.conversation.services.turn_processor import set_pending_forced_user_turn
from backend.conversation.services.turn_processor import set_user_override_requested
from backend.conversation.services.utterance_duplicates import DuplicateDetectionResult
from backend.conversation.services.utterance_duplicates import (
    apply_duplicate_detection_to_turn,
)
from backend.conversation.services.utterance_duplicates import (
    detect_duplicate_agent_utterance,
)

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
MAX_AGENT_COUNT = 3
MAX_MALE_AGENTS = 1

logger = logging.getLogger(__name__)


def log_agent_utterance_duplicate_detection(
    *,
    session: ConversationSession,
    agent_id: str,
    result: DuplicateDetectionResult,
    correlation_id: str,
    turn_index: int,
) -> None:
    if not result.is_duplicate:
        return

    context = result.to_log_context()
    context.update(
        {
            "speaker": agent_id,
            "future_policy": "regeneration_or_replanning_not_implemented",
        },
    )
    TurnEngineLog.objects.create(
        session=session,
        component=TurnEngineLog.COMPONENT_TURN_PROCESSOR,
        level=TurnEngineLog.LEVEL_INFO,
        event="agent_utterance_duplicate_detected",
        message="agent_utterance_duplicate_result_exposed",
        context=context,
        correlation_id=correlation_id,
        turn_index=turn_index,
        subturn_index=0,
    )


def _slugify_agent_id(text: str) -> str:
    """
    Create a stable-ish, URL/ID-safe agent id derived from persona_name.
    """
    import re

    s = str(text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "agent"


def select_agent_personas_for_session(ocean: dict[str, str], *, count: int = 3):
    selected = select_complementary_agent_personas(ocean, count=count)
    if len(selected) < count:
        msg = f"backend/conversation/data/prompts/ must provide at least {count} agent personas"
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
        self._correlation_id: str = ""
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
            requested_agent_count = content.get("agent_count")
            try:
                agent_count = int(requested_agent_count) if requested_agent_count is not None else None
            except Exception:
                agent_count = None
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
            discussion = await self._discussion_context_for_topic(topic)
            try:
                session = await self._create_session(
                    topic=topic,
                    agent_count=agent_count,
                    discussion=discussion,
                )
            except Exception as exc:
                logger.exception("start_session_failed topic=%s", topic[:120])
                await self.send_json(
                    {
                        "type": "error",
                        "message": f"Could not start session: {exc}",
                    },
                )
                return
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
            asyncio.create_task(self._materialize_session_knowledge(session.id, discussion))
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
            self._correlation_id = uuid4().hex
            decision = await database_sync_to_async(decide_next_speaker)(
                session,
                user_volunteered=self.user_volunteered,
                last_user_turn_index=last_user_turn_index,
            )
            await self._log_turn_engine(
                session_id=session.id,
                component=TurnEngineLog.COMPONENT_TURN_MANAGER,
                level=TurnEngineLog.LEVEL_INFO,
                event="decide_next_speaker",
                message=decision.reason,
                context={
                    "turn_count": int(session.turn_count),
                    "pending_forced_user_turn": bool(session.pending_forced_user_turn),
                    "user_override_requested": bool(session.user_override_requested),
                    "user_volunteered": bool(self.user_volunteered),
                    "last_user_turn_index": last_user_turn_index,
                    "decision": {
                        "terminate": bool(decision.terminate),
                        "next_speaker_type": decision.next_speaker_type,
                        "next_speaker_id": decision.next_speaker_id,
                        "reason": decision.reason,
                    },
                },
                correlation_id=self._correlation_id,
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
                persona, agent_display_name = await self._get_agent_persona_and_name(
                    session.id,
                    decision.next_speaker_id,
                )
                # 1) Show "thinking" right away so the user sees the banner immediately.
                await self.send_json({
                    "type": "agent_status",
                    "status": "thinking",
                    "agent_display_name": agent_display_name,
                })
                try:
                    resolved_agent_id, plan = await self._build_plan_for_agent(
                        session.id,
                        decision.next_speaker_id,
                    )
                    # 2) Show searching_online only when web retrieval will actually run.
                    plan_for_retrieval = {
                        **plan,
                        "_agent_persona_name": persona,
                    }
                    retrieval_sources = await self._resolve_agent_retrieval_sources(
                        session.id,
                        plan_for_retrieval,
                    )
                    if "web" in retrieval_sources:
                        await self.send_json({
                            "type": "agent_status",
                            "status": "searching_online",
                            "agent_display_name": agent_display_name,
                        })
                    turn = await self._append_agent_llm_turn(
                        session.id,
                        agent_id=resolved_agent_id,
                        plan=plan,
                    )
                except Exception as e:
                    await self._log_turn_engine(
                        session_id=session.id,
                        component=TurnEngineLog.COMPONENT_TURN_PROCESSOR,
                        level=TurnEngineLog.LEVEL_ERROR,
                        event="append_agent_llm_turn_exception",
                        message=str(e),
                        context={},
                        correlation_id=self._correlation_id,
                    )
                    logger.exception(
                        "append_agent_llm_turn_failed session_id=%s agent_id=%s",
                        session.id,
                        decision.next_speaker_id,
                    )
                    await self.send_json(
                        {
                            "type": "error",
                            "message": f"Agent turn failed: {e}",
                        },
                    )
                    await self.send_json({"type": "agent_status", "status": "finished"})
                    return
                session_after = await self._get_session(self.session_id)
                if session_after is None or session_after.paused or session_after.terminate:
                    return
                await self.send_json({"type": "turn", "turn": await self._turn_to_dict(turn)})
                await self.send_json({"type": "agent_status", "status": "finished"})
                continue

    @database_sync_to_async
    def _resolve_agent_retrieval_sources(
        self,
        session_id: int,
        facilitator_plan: dict,
    ) -> set[str]:
        session = ConversationSession.objects.filter(id=session_id).first()
        if session is None:
            return set()
        return resolve_agent_retrieval_sources(facilitator_plan, session=session)

    @database_sync_to_async
    def _discussion_context_for_topic(self, topic: str) -> dict:
        user = self.scope["user"]
        if not getattr(user, "is_authenticated", False):
            return {}
        user_model = get_user_model()
        user = user_model.objects.select_related("userprofile").get(pk=user.pk)
        profile = getattr(user, "userprofile", None)
        if profile is None:
            return {}
        scenario = str(profile.discussion_scenario or "").strip()
        if not scenario or scenario != str(topic or "").strip():
            return {}
        article_ids = list(profile.discussion_article_ids or [])
        if not article_ids and profile.discussion_article_id:
            article_ids = [profile.discussion_article_id]
        return {
            "news_category": str(profile.discussion_category or ""),
            "news_subtopic": str(profile.discussion_subtopic or ""),
            "scenario": scenario,
            "news_article_id": profile.discussion_article_id,
            "discussion_article_ids": article_ids,
            "discussion_web_context": str(getattr(profile, "discussion_web_context", "") or ""),
        }

    @database_sync_to_async
    def _create_session(
        self,
        *,
        topic: str,
        agent_count: int | None = None,
        discussion: dict | None = None,
    ) -> ConversationSession:
        user = self.scope["user"]
        desired_count = agent_count
        if desired_count is None:
            desired_count = int(getattr(settings, "CONVERSATION_AGENT_COUNT", 3) or 3)
        desired_count = max(1, min(MAX_AGENT_COUNT, int(desired_count)))
        discussion = discussion or {}
        news_article_id = discussion.get("news_article_id")
        discussion_article_ids = list(discussion.get("discussion_article_ids") or [])
        if not discussion_article_ids and news_article_id:
            discussion_article_ids = [int(news_article_id)]
        scenario = str(discussion.get("scenario") or topic or "").strip()
        session = ConversationSession.objects.create(
            user=user,
            topic=topic,
            agent_count=desired_count,
            news_category=str(discussion.get("news_category") or ""),
            news_subtopic=str(discussion.get("news_subtopic") or ""),
            scenario=scenario,
            news_article_id=news_article_id if news_article_id else None,
            discussion_article_ids=discussion_article_ids,
        )
        ocean = user.userprofile.ocean if hasattr(user, "userprofile") else {}
        user_cefr_level = user.userprofile.cefr_level if hasattr(user, "userprofile") else ""
        user_major = user.userprofile.major if hasattr(user, "userprofile") else ""
        agent_cefr_level = normalize_user_cefr_level(user_cefr_level)
        selected_prompts = select_agent_personas_for_session(ocean, count=desired_count)
        used_ids: set[str] = set()
        agent_rows: list[AgentProfile] = []
        male_count = 0
        for idx, selected in enumerate(selected_prompts):
            base = _slugify_agent_id(selected.prompt.persona_name)
            candidate = base
            if candidate in used_ids:
                candidate = f"{base}_{idx + 1}"
            used_ids.add(candidate)
            gender = "female" if male_count >= MAX_MALE_AGENTS else None
            voice_preset = pick_voice_preset_for_persona(selected.prompt.persona_name, gender=gender)
            if voice_preset.gender == "male":
                male_count += 1
            agent_rows.append(
                AgentProfile(
                    session=session,
                    agent_id=candidate,
                    display_name=voice_preset.name,
                    personality={
                        "persona_name": selected.prompt.persona_name,
                        "source_trait": selected.source_trait,
                        "user_level": selected.user_level,
                        "major": user_major,
                        "voice_chinese_name": voice_preset.chinese_name,
                        "voice_gender": voice_preset.gender,
                        "voice_title": voice_preset.title,
                    },
                    voice=provider_voice_id(voice_preset),
                    traits={
                        "style": selected.prompt.persona_name.lower().replace(" ", "_"),
                        "proficiency_level": agent_cefr_level,
                        "complementary_score": selected.complementary_score,
                    },
                ),
            )
        AgentProfile.objects.bulk_create(agent_rows)
        return session

    @database_sync_to_async
    def _materialize_session_knowledge_sync(
        self,
        session_id: int,
        discussion: dict,
    ) -> None:
        session = ConversationSession.objects.filter(id=session_id).first()
        if session is None:
            return
        discussion_article_ids = list(discussion.get("discussion_article_ids") or [])
        news_article_id = discussion.get("news_article_id")
        if not discussion_article_ids and news_article_id:
            discussion_article_ids = [int(news_article_id)]
        try:
            if discussion_article_ids:
                materialize_session_news_knowledge(session, discussion_article_ids)
                return
            web_context = str(discussion.get("discussion_web_context") or "").strip()
            if web_context:
                materialize_session_web_knowledge(session, web_context)
        except Exception:
            logger.exception(
                "session_knowledge_materialize_failed session_id=%s article_ids=%s has_web=%s",
                session_id,
                discussion_article_ids,
                bool(discussion.get("discussion_web_context")),
            )

    async def _materialize_session_knowledge(
        self,
        session_id: int,
        discussion: dict,
    ) -> None:
        await self._materialize_session_knowledge_sync(session_id, discussion)

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
            voice_gender = (a.personality or {}).get("voice_gender") or ""
            avatar_body = "M" if str(voice_gender).strip().lower() in {"m", "male"} else "F"
            participants.append(
                {
                    "id": a.agent_id,
                    "name": a.display_name or a.agent_id,
                    "type": "agent",
                    "persona_name": (a.personality or {}).get("persona_name") or "",
                    "gender": voice_gender,
                    "voice_title": (a.personality or {}).get("voice_title") or "",
                    "avatar_body": avatar_body,
                },
            )
        return participants

    @database_sync_to_async
    def _get_agent_persona_and_name(self, session_id: int, agent_id: str) -> tuple[str, str]:
        agent = AgentProfile.objects.filter(session_id=session_id, agent_id=agent_id).only(
            "personality",
            "display_name",
            "agent_id",
        ).first()
        if not agent:
            return "", ""
        persona = str((agent.personality or {}).get("persona_name") or "")
        display_name = (agent.display_name or agent.agent_id or "").strip()
        return persona, display_name

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
        TurnEngineLog.objects.create(
            session=session,
            component=TurnEngineLog.COMPONENT_TURN_PROCESSOR,
            level=TurnEngineLog.LEVEL_INFO,
            event="process_user_turn",
            message="user_turn_appended",
            context={
                "turn_count_after": int(processed.session.turn_count),
                "speaker": processed.turn.speaker,
                "speaker_type": processed.turn.speaker_type,
                "turn_index": int(processed.turn.turn_index),
                "subturn_index": int(getattr(processed.turn, "subturn_index", 0)),
                "speech_act": processed.turn.speech_act,
                "subtype": processed.turn.subtype,
                "target": processed.turn.target,
                "source": source,
                "has_audio_url": bool(processed.turn.audio_url),
            },
            correlation_id=self._correlation_id,
            turn_index=processed.turn.turn_index,
            subturn_index=getattr(processed.turn, "subturn_index", 0),
        )
        # Once the user has spoken, clear any "forced user" + override flags.
        if processed.session.pending_forced_user_turn:
            set_pending_forced_user_turn(processed.session, pending=False)
        set_user_override_requested(processed.session, requested=False)
        return processed.turn

    @database_sync_to_async
    def _build_plan_for_agent(self, session_id: int, agent_id: str | None) -> tuple[str, dict]:
        """Resolve the agent and run the facilitator step.

        Returns the resolved agent_id and the facilitator plan so the caller can
        inspect plan["type"] (e.g. to decide whether to show "checking online" UI)
        before the rest of the turn pipeline executes.
        """
        session = ConversationSession.objects.get(id=session_id)
        if agent_id:
            agent = AgentProfile.objects.get(session=session, agent_id=agent_id)
        elif session.turn_count == 0:
            agents = list(AgentProfile.objects.filter(session=session))
            if not agents:
                msg = "Session has no agent profiles configured."
                raise ValueError(msg)
            agent = max(agents, key=lambda a: float(a.traits.get("leadership", 0.0)))
        else:
            agents = list(AgentProfile.objects.filter(session=session).order_by("agent_id"))
            if not agents:
                msg = "Session has no agent profiles configured."
                raise ValueError(msg)
            agent = agents[int(session.turn_count) % len(agents)]
        plan = build_facilitator_plan(session, agent=agent)
        return agent.agent_id, plan

    async def _synthesize_agent_audio(
        self,
        *,
        text: str,
        voice: str,
    ) -> tuple[str | None, dict | None, int | None]:
        """
        Run TTS off the DB thread so a slow Fish API call cannot block admin/HTTP.
        """
        connect_timeout, read_timeout = tts_provider_timeouts()
        # Wait for TTS to finish; small buffer over HTTP read timeout.
        tts_timeout = connect_timeout + read_timeout + 10.0
        t_tts0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    synthesize_speech_with_lipsync,
                    text=text,
                    voice=voice,
                ),
                timeout=tts_timeout,
            )
            t_tts_ms = int((time.perf_counter() - t_tts0) * 1000)
            return result.audio_url, result.lipsync, t_tts_ms
        except Exception:
            logger.exception(
                "agent_tts_failed voice=%s text_chars=%d timeout_sec=%.0f",
                voice,
                len(text),
                tts_timeout,
            )
            return None, None, None

    async def _append_agent_llm_turn(
        self,
        session_id: int,
        *,
        agent_id: str | None = None,
        plan: dict | None = None,
    ) -> TurnRecord:
        prep = await self._prepare_agent_llm_turn(
            session_id,
            agent_id=agent_id,
            plan=plan,
        )
        voice = prep["voice"]
        audio_url, lipsync, t_tts_ms = await self._synthesize_agent_audio(
            text=prep["utterance_tts"],
            voice=voice,
        )
        return await self._finalize_agent_llm_turn(
            prep,
            audio_url=audio_url,
            lipsync=lipsync,
            t_tts_ms=t_tts_ms,
        )

    @database_sync_to_async
    def _prepare_agent_llm_turn(
        self,
        session_id: int,
        *,
        agent_id: str | None = None,
        plan: dict | None = None,
    ) -> dict:
        session = ConversationSession.objects.get(id=session_id)
        if agent_id:
            agent = AgentProfile.objects.get(session=session, agent_id=agent_id)
        elif session.turn_count == 0:
            # First agent turn (when user didn't speak first): pick highest leadership.
            agents = list(AgentProfile.objects.filter(session=session))
            if not agents:
                msg = "Session has no agent profiles configured."
                raise ValueError(msg)
            agent = max(agents, key=lambda a: float(a.traits.get("leadership", 0.0)))
        else:
            agents = list(AgentProfile.objects.filter(session=session).order_by("agent_id"))
            if not agents:
                msg = "Session has no agent profiles configured."
                raise ValueError(msg)
            agent = agents[int(session.turn_count) % len(agents)]
        agent_id = agent.agent_id

        t0 = time.perf_counter()
        if plan is None:
            plan = build_facilitator_plan(session, agent=agent)
        TurnEngineLog.objects.create(
            session=session,
            component=TurnEngineLog.COMPONENT_TURN_PROCESSOR,
            level=TurnEngineLog.LEVEL_INFO,
            event="agent_turn_start",
            message="start_agent_turn_pipeline",
            context={
                "speaker": agent_id,
                "turn_count_before": int(session.turn_count),
            },
            correlation_id=self._correlation_id,
            turn_index=int(session.turn_count),
            subturn_index=0,
        )

        t_utter0 = time.perf_counter()
        generated = generate_agent_utterance_with_retrieval(session, agent=agent, facilitator_plan=plan)
        t_utter_ms = int((time.perf_counter() - t_utter0) * 1000)
        utterance = generated.utterance
        duplicate_result = detect_duplicate_agent_utterance(session, utterance)
        log_agent_utterance_duplicate_detection(
            session=session,
            agent_id=agent_id,
            result=duplicate_result,
            correlation_id=self._correlation_id,
            turn_index=int(session.turn_count),
        )

        return {
            "session": session,
            "agent_id": agent_id,
            "plan": plan,
            "utterance": utterance,
            "utterance_tts": generated.utterance_tts,
            "generated": generated,
            "duplicate_result": duplicate_result,
            "t_utter_ms": t_utter_ms,
            "t0": t0,
            "voice": agent.voice or "alloy",
        }

    @database_sync_to_async
    def _finalize_agent_llm_turn(
        self,
        prep: dict,
        *,
        audio_url: str | None,
        lipsync: dict | None,
        t_tts_ms: int | None,
    ) -> TurnRecord:
        session = prep["session"]
        agent_id = prep["agent_id"]
        plan = prep["plan"]
        utterance = prep["utterance"]
        generated = prep["generated"]
        duplicate_result = prep["duplicate_result"]
        t_utter_ms = prep["t_utter_ms"]
        t0 = prep["t0"]

        processed = process_agent_turn(
            session,
            speaker=agent_id,
            utterance=utterance,
            utterance_tts=prep["utterance_tts"],
            facilitator_plan=plan,
            source="llm",
            audio_url=audio_url,
            lipsync=lipsync,
        )
        apply_duplicate_detection_to_turn(processed.turn, duplicate_result)
        persist_turn_retrieval_safely(processed.turn, generated.retrieval_context)
        total_ms = int((time.perf_counter() - t0) * 1000)
        TurnEngineLog.objects.create(
            session=session,
            component=TurnEngineLog.COMPONENT_TURN_PROCESSOR,
            level=TurnEngineLog.LEVEL_INFO,
            event="process_agent_turn",
            message="agent_turn_appended",
            context={
                "turn_count_after": int(processed.session.turn_count),
                "speaker": processed.turn.speaker,
                "speaker_type": processed.turn.speaker_type,
                "turn_index": int(processed.turn.turn_index),
                "subturn_index": int(getattr(processed.turn, "subturn_index", 0)),
                "speech_act": processed.turn.speech_act,
                "subtype": processed.turn.subtype,
                "target": processed.turn.target,
                "source": "llm",
                "has_audio_url": bool(processed.turn.audio_url),
                "timing_ms": {
                    "utterance_with_retrieval": t_utter_ms,
                    "tts": t_tts_ms,
                    "total": total_ms,
                },
            },
            correlation_id=self._correlation_id,
            turn_index=processed.turn.turn_index,
            subturn_index=getattr(processed.turn, "subturn_index", 0),
        )
        return processed.turn

    @database_sync_to_async
    def _log_turn_engine(
        self,
        *,
        session_id: int,
        component: str,
        level: str,
        event: str,
        message: str,
        context: dict,
        correlation_id: str = "",
        turn_index: int | None = None,
        subturn_index: int | None = None,
    ) -> None:
        session = ConversationSession.objects.get(id=session_id)
        TurnEngineLog.objects.create(
            session=session,
            component=component,
            level=level,
            event=event,
            message=message,
            context=context or {},
            correlation_id=correlation_id or "",
            turn_index=turn_index,
            subturn_index=subturn_index,
        )

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
            "lipsync": turn.lipsync,
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        }
