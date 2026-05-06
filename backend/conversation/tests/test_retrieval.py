from django.contrib import admin
from django.test import RequestFactory
from django.test import override_settings
import pytest

from backend.conversation.admin import TurnRetrievalAdmin
from backend.conversation.models import ConversationSession
from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.services.retrieval import RetrievedContext
from backend.conversation.services.retrieval import RetrievedItem
from backend.conversation.services.retrieval import map_retrieval_sources
from backend.conversation.services.retrieval import persist_turn_retrieval
from backend.conversation.services.retrieval import retrieve
from backend.conversation.services.turn_processor import append_turn
from backend.users.tests.factories import UserFactory


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


@pytest.mark.django_db
def test_turn_retrieval_admin_disables_add_delete_permissions(user) -> None:
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])

    request = RequestFactory().get("/admin/conversation/turnretrieval/")
    request.user = user
    model_admin = TurnRetrievalAdmin(TurnRetrieval, admin.site)

    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_change_permission(request) is True


def test_map_retrieval_sources() -> None:
    assert map_retrieval_sources("web_search") == {"web", "knowledge"}
    assert map_retrieval_sources("web search") == {"web", "knowledge"}
    assert map_retrieval_sources("memory") == {"memory", "session", "knowledge"}
    assert map_retrieval_sources("none") == set()
    assert map_retrieval_sources("") == set()
    assert map_retrieval_sources("exemplar") == set()
    assert map_retrieval_sources("surprise") == set()


@pytest.mark.django_db
def test_retrieve_no_sources_returns_prompt_safe_message(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="retrieval")

    context = retrieve(
        "anything",
        session=session,
        user=user,
        sources=set(),
        top_k=5,
    )

    assert context.items == []
    assert context.source_statuses == {"none": "skipped"}
    assert "No retrieval requested" in context.rendered_context


@pytest.mark.django_db
def test_retrieve_unsupported_source_is_skipped(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="retrieval")

    context = retrieve(
        "anything",
        session=session,
        user=user,
        sources={"unknown"},
        top_k=5,
    )

    assert context.items == []
    assert context.source_statuses == {"unknown": "skipped"}
    assert "conversation context only" in context.rendered_context


@pytest.mark.django_db
def test_memory_source_returns_not_configured(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="memory")

    context = retrieve("my goals", session=session, user=user, sources={"memory"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["memory"] == "not-configured"
    assert "conversation context only" in context.rendered_context


@pytest.mark.django_db
@override_settings(WEB_SEARCH_ENABLED=False, WEB_SEARCH_API_URL="https://example.com/search")
def test_web_source_disabled_returns_prompt_safe_status(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="climate")

    context = retrieve("Topic: climate", session=session, user=user, sources={"web"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["web"] == "skipped"
    assert context.source_messages["web"].startswith("(Web search is disabled")
    assert "Web search is disabled" in context.rendered_context
    assert "conversation context only" in context.rendered_context


@pytest.mark.django_db
def test_web_source_wraps_fetch_result_as_item(user, monkeypatch) -> None:
    session = ConversationSession.objects.create(user=user, topic="climate")
    fetched = "1.\n   Title: Climate outlook\n   Organization: NOAA\n   Excerpt: Sea levels rose."
    monkeypatch.setattr(
        "backend.conversation.services.retrieval.fetch_web_search_context",
        lambda query: fetched,
    )

    context = retrieve("Topic: climate", session=session, user=user, sources={"web"}, top_k=5)

    assert context.source_statuses["web"] == "success"
    assert len(context.items) == 1
    assert context.items[0].source == "web"
    assert context.items[0].excerpt == fetched
    assert context.items[0].metadata["search_query"] == "Topic: climate"
    assert "Climate outlook" in context.rendered_context


@pytest.mark.django_db
def test_session_source_finds_earlier_turn(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="planning")
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I want to practice climate policy debates.",
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Let's start with introductions.",
    )
    append_turn(
        session,
        speaker="agent_2",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="We can discuss tradeoffs.",
    )
    append_turn(
        session,
        speaker="agent_3",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Recent context should be excluded if configured.",
    )

    context = retrieve("climate policy", session=session, user=user, sources={"session"}, top_k=5)

    assert context.source_statuses["session"] == "success"
    assert len(context.items) == 1
    assert context.items[0].source == "session"
    assert context.items[0].metadata["turn_index"] == 0
    assert "climate policy" in context.items[0].excerpt


@pytest.mark.django_db
def test_session_source_skips_sessions_owned_by_another_user(user) -> None:
    other_user = UserFactory()
    session = ConversationSession.objects.create(user=other_user, topic="planning")
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I want to practice private climate policy debates.",
    )

    context = retrieve("climate policy", session=session, user=user, sources={"session"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["session"] == "skipped"
    assert "conversation context only" in context.rendered_context


@pytest.mark.django_db
def test_mixed_sources_are_ranked_globally_before_top_k(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="planning")
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="climate policy climate policy climate policy",
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="recent one",
    )
    append_turn(
        session,
        speaker="agent_2",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="recent two",
    )
    append_turn(
        session,
        speaker="agent_3",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="recent three",
    )
    KnowledgeSnippet.objects.create(
        title="Local note",
        content="climate",
        source_uri="course://climate",
        source_label="Course Handbook",
    )

    context = retrieve("climate policy", session=session, user=user, sources={"knowledge", "session"}, top_k=1)

    assert len(context.items) == 1
    assert context.items[0].source == "session"
    assert context.items[0].metadata["turn_index"] == 0


@pytest.mark.django_db
def test_knowledge_source_returns_citation(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Seminar participation policy",
        content="Students should cite the course handbook when discussing attendance.",
        source_uri="course://handbook#participation",
        source_label="Course Handbook",
    )

    context = retrieve("attendance handbook", session=session, user=user, sources={"knowledge"}, top_k=5)

    assert context.source_statuses["knowledge"] == "success"
    assert context.items[0].source == "knowledge"
    assert context.items[0].title == "Seminar participation policy"
    assert context.items[0].source_uri == "course://handbook#participation"
    assert "Seminar participation policy" in context.rendered_context


@pytest.mark.django_db
def test_knowledge_source_reports_no_results(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")

    context = retrieve("attendance handbook", session=session, user=user, sources={"knowledge"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["knowledge"] == "no-results"


@pytest.mark.django_db
def test_persist_turn_retrieval_stores_trace_for_agent_turn(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    processed = append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="The handbook covers participation.",
        source="llm",
    )
    context = RetrievedContext(
        query="attendance handbook",
        requested_sources=["web", "knowledge"],
        source_statuses={"web": "success", "knowledge": "success"},
        items=[
            RetrievedItem(
                source="web",
                title="Attendance policy",
                excerpt="Students should attend.",
                metadata={"search_query": "attendance handbook"},
            ),
            RetrievedItem(
                source="knowledge",
                title="Course handbook",
                excerpt="Participation matters.",
                source_uri="course://handbook",
            ),
        ],
        rendered_context="Retrieved information:\n1. Source: web",
    )

    trace = persist_turn_retrieval(processed.turn, context)

    assert trace.turn == processed.turn
    assert trace.query == "attendance handbook"
    assert trace.requested_sources == ["web", "knowledge"]
    assert trace.source_statuses == {"web": "success", "knowledge": "success"}
    assert trace.items[0]["metadata"]["search_query"] == "attendance handbook"
    assert trace.rendered_context == "Retrieved information:\n1. Source: web"
