from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.makeshift import invite_user
from backend.conversation.services.facilitator import build_facilitator_plan
from backend.conversation.services.agent import generate_agent_utterance
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import mark_terminate
from backend.conversation.services.turn_processor import set_pending_forced_user_turn
from backend.conversation.services.tts import synthesize_speech


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
        await self.send_json(
            {
                "type": "connected",
                "user_id": user.pk,
            },
        )

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")

        if msg_type == "start_session":
            topic = str(content.get("topic") or "")
            session = await self._create_session(topic=topic)
            self.session_id = session.id
            await self.send_json(
                {
                    "type": "session_started",
                    "session_id": session.id,
                    "topic": session.topic,
                },
            )
            await self._advance_loop()
            return

        if msg_type == "volunteer":
            self.user_volunteered = True
            await self.send_json({"type": "user_volunteered"})
            await self._advance_loop()
            return

        if msg_type == "end_session":
            if self.session_id is not None:
                await self._mark_terminate(self.session_id)
            await self.send_json({"type": "session_ended"})
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
            await self._append_user_turn(self.session_id, utterance=utterance, source=source)
            await self._advance_loop()
            return

        await self.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    async def _advance_loop(self):
        """
        Advances the conversation by generating the next non-user turns (agent/makeshift).
        If a user turn is needed, it will emit a `need_user_turn` event and stop.
        """
        if self.session_id is None:
            return

        while True:
            session = await self._get_session(self.session_id)
            if session is None:
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

            assert decision.next_speaker is not None
            if decision.next_speaker == "user":
                self.user_volunteered = False
                if session.pending_forced_user_turn:
                    await self._set_pending_forced_user_turn(session.id, pending=False)
                await self.send_json({"type": "need_user_turn", "reason": decision.reason})
                return

            if decision.next_speaker == "makeshift":
                turn = await self._invite_user(session.id)
                await self.send_json({"type": "turn", "turn": self._turn_to_dict(turn)})
                continue

            if decision.next_speaker == "agent":
                await self.send_json({"type": "agent_status", "status": "thinking"})
                turn = await self._append_agent_llm_turn(session.id)
                await self.send_json({"type": "turn", "turn": self._turn_to_dict(turn)})
                await self.send_json({"type": "agent_status", "status": "finished"})
                continue

    @database_sync_to_async
    def _create_session(self, *, topic: str) -> ConversationSession:
        user = self.scope["user"]
        session = ConversationSession.objects.create(user=user, topic=topic)
        AgentProfile.objects.bulk_create(
            [
                AgentProfile(
                    session=session,
                    agent_id="agent_1",
                    personality={"role": "pro"},
                    traits={"style": "structured"},
                ),
                AgentProfile(
                    session=session,
                    agent_id="agent_2",
                    personality={"role": "con"},
                    traits={"style": "critical"},
                ),
                AgentProfile(
                    session=session,
                    agent_id="agent_3",
                    personality={"role": "mediator"},
                    traits={"style": "balanced"},
                ),
            ],
        )
        return session

    @database_sync_to_async
    def _get_session(self, session_id: int) -> ConversationSession | None:
        user = self.scope["user"]
        return ConversationSession.objects.filter(id=session_id, user=user).first()

    @database_sync_to_async
    def _mark_terminate(self, session_id: int) -> None:
        session = ConversationSession.objects.get(id=session_id)
        mark_terminate(session)

    @database_sync_to_async
    def _append_user_turn(self, session_id: int, *, utterance: str, source: str) -> TurnRecord:
        session = ConversationSession.objects.get(id=session_id)
        processed = append_turn(
            session,
            speaker="user",
            speaker_type=TurnRecord.SPEAKER_TYPE_USER,
            utterance=utterance,
            speech_act="ASSERTIVES",
            subtype="opinion",
            target=None,
            source=source,
        )
        return processed.turn

    @database_sync_to_async
    def _append_agent_llm_turn(self, session_id: int) -> TurnRecord:
        session = ConversationSession.objects.get(id=session_id)
        idx = (session.turn_count % 3) + 1
        agent_id = f"agent_{idx}"
        agent = AgentProfile.objects.get(session=session, agent_id=agent_id)

        plan = build_facilitator_plan(session, agent=agent)
        utterance = generate_agent_utterance(session, agent=agent, facilitator_plan=plan)
        audio_url = None
        try:
            voice = agent.voice or "alloy"
            audio_url = synthesize_speech(text=utterance, voice=voice)
        except Exception:
            # If TTS fails (missing key, etc.), continue without audio.
            audio_url = None

        processed = append_turn(
            session,
            speaker=agent_id,
            speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
            utterance=utterance,
            speech_act=str(plan.get("type") or ""),
            subtype=plan.get("subtype"),
            target=plan.get("target"),
            source="llm",
            audio_url=audio_url,
        )
        return processed.turn

    @database_sync_to_async
    def _invite_user(self, session_id: int) -> TurnRecord:
        session = ConversationSession.objects.get(id=session_id)
        return invite_user(session)

    @database_sync_to_async
    def _set_pending_forced_user_turn(self, session_id: int, *, pending: bool) -> None:
        session = ConversationSession.objects.get(id=session_id)
        set_pending_forced_user_turn(session, pending=pending)

    @database_sync_to_async
    def _last_user_turn_index(self, session_id: int) -> int | None:
        last = (
            TurnRecord.objects.filter(session_id=session_id, speaker_type=TurnRecord.SPEAKER_TYPE_USER)
            .order_by("-turn_index")
            .first()
        )
        return last.turn_index if last else None

    @staticmethod
    def _turn_to_dict(turn: TurnRecord) -> dict:
        return {
            "speaker": turn.speaker,
            "speaker_type": turn.speaker_type,
            "utterance": turn.utterance,
            "speech_act": turn.speech_act,
            "subtype": turn.subtype,
            "target": turn.target,
            "turn_index": turn.turn_index,
            "source": turn.source,
            "audio_url": turn.audio_url,
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        }

