import pytest

from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.services.turn_processor import append_turn


@pytest.mark.django_db
def test_knowledge_snippet_string_uses_title() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples during discussion.",
        source_uri="course://policy",
        source_label="Course Handbook",
    )

    assert str(snippet) == "Course policy"


@pytest.mark.django_db
def test_turn_retrieval_links_to_agent_turn(user) -> None:
    from backend.conversation.models import ConversationSession

    session = ConversationSession.objects.create(user=user, topic="class discussion")
    processed = append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Use the course policy.",
        source="llm",
    )

    trace = TurnRetrieval.objects.create(
        turn=processed.turn,
        query="course policy",
        requested_sources=["knowledge"],
        source_statuses={"knowledge": "success"},
        items=[{"source": "knowledge", "title": "Course policy"}],
        rendered_context="Knowledge: Course policy",
    )

    assert trace.turn == processed.turn
    assert str(trace) == f"TurnRetrieval(turn={processed.turn.id}, query=course policy)"
