"""
AI-simulated student turns.

Lets a conversation run without a person typing: when it is the learner's turn, an LLM
speaks for them. Used for experiment runs; gated behind SIMULATED_STUDENT_ENABLED and
off by default.
"""

from __future__ import annotations

from django.conf import settings
from langchain_core.messages import SystemMessage

from backend.conversation.models import ConversationSession
from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.llm_tracing import invoke_chat_llm

SIMULATED_TURN_SOURCE = "simulated_student"


def simulated_student_enabled() -> bool:
    return bool(getattr(settings, "SIMULATED_STUDENT_ENABLED", False))


def simulated_student_skip_tts() -> bool:
    """Agent audio is dead weight in an unattended run."""
    return bool(getattr(settings, "SIMULATED_STUDENT_SKIP_TTS", True))


def generate_simulated_student_utterance(session: ConversationSession) -> str:
    """One spoken turn for the learner."""
    profile = getattr(session.user, "userprofile", None)
    ocean = getattr(profile, "ocean", None) or {}

    # The student always sees the WHOLE conversation, whatever CONVERSATION_FULL_CONTEXT
    # is set to. A real participant heard every turn; the short window is an agent-side
    # limitation under test, and narrowing the student here would confound the comparison.
    prompt = render_prompt_template(
        load_additional_prompt("simulated_student.txt"),
        student_name=getattr(profile, "preferred_name", "") or "the student",
        student_major=getattr(profile, "major", "") or "not specified",
        cefr_level=getattr(profile, "cefr_level", "") or "B1",
        ocean=", ".join(f"{trait}={level}" for trait, level in sorted(ocean.items())) or "not specified",
        topic=session.topic or "(no topic recorded)",
        history=build_numbered_transcript(session) or "(the discussion has not started yet)",
    )

    llm = get_default_chat_llm()
    result = invoke_chat_llm(llm, [SystemMessage(content=prompt)], user=session.user)
    raw = result.content if hasattr(result, "content") else str(result)
    return " ".join(str(raw).split())
