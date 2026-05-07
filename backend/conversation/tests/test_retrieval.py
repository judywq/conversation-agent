import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.test import override_settings

from backend.conversation.admin import TurnRetrievalAdmin
from backend.conversation.models import ConversationSession
from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.services import retrieval as retrieval_service
from backend.conversation.services.embeddings import fake_embedding
from backend.conversation.services.retrieval import RetrievedContext
from backend.conversation.services.retrieval import RetrievedItem
from backend.conversation.services.retrieval import map_retrieval_sources
from backend.conversation.services.retrieval import persist_turn_retrieval
from backend.conversation.services.retrieval import persist_turn_retrieval_safely
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
    assert map_retrieval_sources("exemplar") == {"exemplar"}
    assert map_retrieval_sources("speech_act_exemplar") == {"exemplar"}
    assert map_retrieval_sources("speech act exemplar") == {"exemplar"}
    assert map_retrieval_sources("surprise") == {"surprise"}


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
def test_web_source_failed_request_returns_failed_status(user, monkeypatch) -> None:
    session = ConversationSession.objects.create(user=user, topic="climate")
    monkeypatch.setattr(
        "backend.conversation.services.retrieval.fetch_web_search_context",
        lambda query: "(Web search failed; proceed without verified external facts.)",
    )

    context = retrieve("Topic: climate", session=session, user=user, sources={"web"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["web"] == "failed"
    assert "Web search failed" in context.source_messages["web"]
    assert "Web search failed" in context.rendered_context


@pytest.mark.django_db
def test_web_source_empty_result_returns_no_results_status(user, monkeypatch) -> None:
    session = ConversationSession.objects.create(user=user, topic="climate")
    monkeypatch.setattr(
        "backend.conversation.services.retrieval.fetch_web_search_context",
        lambda query: "(Web search returned no usable snippets.)",
    )

    context = retrieve("Topic: climate", session=session, user=user, sources={"web"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["web"] == "no-results"
    assert "no usable snippets" in context.source_messages["web"]
    assert "no usable snippets" in context.rendered_context


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
@override_settings(EMBEDDING_PROVIDER="fake")
def test_mixed_sources_keep_strong_knowledge_result_with_global_top_k(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="planning")
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="policy",
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
        title="Policy policy policy",
        content="policy policy policy policy policy",
        source_uri="course://policy",
        source_label="Policy Handbook",
    )

    context = retrieve(
        "policy",
        session=session,
        user=user,
        sources={"knowledge", "session"},
        top_k=1,
    )

    assert len(context.items) == 1
    assert context.items[0].source == "knowledge"
    assert context.items[0].score > 1.0
    assert context.items[0].metadata["rerank_score"] < context.items[0].score


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake")
def test_knowledge_source_returns_citation(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Seminar participation policy",
        content="Students should cite the course handbook when discussing attendance.",
        source_uri="course://handbook#participation",
        source_label="Course Handbook",
    )

    context = retrieve(
        "attendance handbook",
        session=session,
        user=user,
        sources={"knowledge"},
        top_k=5,
    )

    assert context.source_statuses["knowledge"] == "success"
    assert context.items[0].source == "knowledge"
    assert context.items[0].title == "Seminar participation policy"
    assert context.items[0].source_uri == "course://handbook#participation"
    assert context.items[0].metadata["retrieval_channels"] == ["keyword"]
    assert context.items[0].metadata["rerank_score"] > 0
    assert "Seminar participation policy" in context.rendered_context


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake")
def test_hybrid_knowledge_metadata_keeps_source_status_string(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Attendance handbook",
        content="Students should cite the course handbook when discussing attendance.",
        source_uri="course://handbook#attendance",
        source_label="Course Handbook",
        metadata={"section": "attendance"},
    )

    context = retrieve("attendance handbook", session=session, user=user, sources={"knowledge"}, top_k=5)

    assert context.source_statuses["knowledge"] == "success"
    assert isinstance(context.source_statuses["knowledge"], str)
    assert context.items[0].metadata["knowledge_snippet_id"] is not None
    assert context.items[0].metadata["metadata"] == {"section": "attendance"}
    assert context.items[0].metadata["retrieval_channels"] == ["keyword"]
    assert context.items[0].metadata["keyword_score"] > 0
    assert context.items[0].metadata["keyword_rank"] == 1
    assert context.items[0].metadata["vector_similarity"] is None
    assert context.items[0].metadata["vector_rank"] is None
    assert context.items[0].metadata["rerank_score"] > 0
    assert context.items[0].metadata["embedding_model"] == ""


@pytest.mark.django_db
@override_settings(
    EMBEDDING_PROVIDER="fake",
    HYBRID_RRF_K=10,
    HYBRID_KEYWORD_WEIGHT=1.0,
    HYBRID_VECTOR_WEIGHT=1.0,
)
def test_hybrid_duplicate_candidate_is_merged(user, monkeypatch) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    matching = KnowledgeSnippet.objects.create(
        title="Attendance handbook",
        content="Students should cite the course handbook when discussing attendance.",
        source_uri="course://handbook#attendance",
        source_label="Course Handbook",
        metadata={"section": "attendance"},
        embedding=[0.1] * 1536,
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    def vector_candidates(query, *, candidate_count):
        return (
            [
                retrieval_service._KnowledgeCandidate(
                    snippet=matching,
                    vector_similarity=0.75,
                    vector_rank=1,
                    embedding_model="fake",
                ),
            ],
            "success",
        )

    monkeypatch.setattr(
        retrieval_service,
        "_vector_knowledge_candidates",
        vector_candidates,
    )

    context = retrieve(
        "attendance handbook",
        session=session,
        user=user,
        sources={"knowledge"},
        top_k=5,
    )

    assert context.source_statuses["knowledge"] == "success"
    assert len(context.items) == 1
    item = context.items[0]
    assert item.metadata["knowledge_snippet_id"] == matching.id
    assert item.metadata["retrieval_channels"] == ["keyword", "vector"]
    assert item.metadata["keyword_score"] > 0
    assert item.metadata["keyword_rank"] == 1
    assert item.metadata["vector_similarity"] == 0.75
    assert item.metadata["vector_rank"] == 1
    assert item.metadata["embedding_model"] == "fake"
    assert item.metadata["rerank_score"] == pytest.approx((1 / 11) + (1 / 11))


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_vector_recall_ignores_stale_embedding_model_or_dimensions(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    query = "semantic-only-query"
    KnowledgeSnippet.objects.create(
        title="Wrong model",
        content="unrelated content",
        source_uri="course://wrong-model",
        source_label="Archive",
        embedding=fake_embedding(query),
        embedding_model="old-model",
        embedding_dimensions=1536,
    )
    KnowledgeSnippet.objects.create(
        title="Wrong dimensions",
        content="unrelated content",
        source_uri="course://wrong-dimensions",
        source_label="Archive",
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=512,
    )
    matching = KnowledgeSnippet.objects.create(
        title="Current embedding",
        content="unrelated content",
        source_uri="course://current",
        source_label="Archive",
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    context = retrieve(
        query,
        session=session,
        user=user,
        sources={"knowledge"},
        top_k=5,
    )

    assert context.source_statuses["knowledge"] == "success"
    assert len(context.items) == 1
    assert context.items[0].metadata["knowledge_snippet_id"] == matching.id
    assert context.items[0].metadata["retrieval_channels"] == ["vector"]
    assert context.items[0].metadata["embedding_model"] == "fake"


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake")
def test_knowledge_source_reports_failed_when_vector_fails_without_keyword_hits(
    user,
    monkeypatch,
) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Semantic only",
        content="unrelated content",
        source_uri="course://semantic",
        source_label="Archive",
        embedding=[0.1] * 1536,
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    def fail_embedding(query):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(retrieval_service, "generate_embedding", fail_embedding)

    context = retrieve(
        "attendance handbook",
        session=session,
        user=user,
        sources={"knowledge"},
        top_k=5,
    )

    assert context.items == []
    assert context.source_statuses["knowledge"] == "failed"


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_knowledge_source_excludes_speech_act_exemplars(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    query = "clarify point"
    KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/request_info #12",
        content="Could you clarify what you mean by that point?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-1",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
        },
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    context = retrieve(query, session=session, user=user, sources={"knowledge"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["knowledge"] == "no-results"


@pytest.mark.django_db
def test_knowledge_source_reports_no_results(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")

    context = retrieve("attendance handbook", session=session, user=user, sources={"knowledge"}, top_k=5)

    assert context.items == []
    assert context.source_statuses["knowledge"] == "no-results"


@pytest.mark.django_db
def test_exemplar_source_returns_active_matching_snippet_with_provenance(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    matching = KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/request_info #12",
        content="Could you clarify what you mean by that point?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-1",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "CDIS01A.txt",
            "previous_sentence": "We were comparing two policies.",
            "next_sentence": "That would help me understand your stance.",
            "import_key": "import-key-1",
        },
    )
    KnowledgeSnippet.objects.create(
        title="Inactive exemplar",
        content="Could you clarify what you mean by that point?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-2",
        source_label="CDIS01A.txt",
        is_active=False,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-2",
        },
    )
    KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Could you clarify what you mean by that point?",
        source_uri="course://policy",
        source_label="Course Handbook",
        is_active=True,
        metadata={
            "kind": "course_policy",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "Course Handbook",
            "import_key": "policy",
        },
    )

    context = retrieve(
        "clarify point",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="directives",
        speech_act_subtype="request_info",
    )

    assert context.source_statuses["exemplar"] == "success"
    assert len(context.items) == 1
    item = context.items[0]
    assert item.source == "exemplar"
    assert item.title == matching.title
    assert item.excerpt == "Could you clarify what you mean by that point?"
    assert item.source_uri == "elfa-sa://CDIS01A.txt#import-key-1"
    assert item.source_label == "CDIS01A.txt"
    assert item.metadata["knowledge_snippet_id"] == matching.id
    assert item.metadata["kind"] == "speech_act_exemplar"
    assert item.metadata["SA_type"] == "DIRECTIVES"
    assert item.metadata["subtype"] == "request_info"
    assert item.metadata["file_name"] == "CDIS01A.txt"
    assert item.metadata["previous_sentence"] == "We were comparing two policies."
    assert (
        item.metadata["next_sentence"] == "That would help me understand your stance."
    )
    assert item.metadata["import_key"] == "import-key-1"
    assert item.metadata["metadata"]["kind"] == "speech_act_exemplar"
    assert "CDIS01A DIRECTIVES/request_info #12" in context.rendered_context
    assert "Speech Act: DIRECTIVES/request_info" in context.rendered_context
    assert "Source file: CDIS01A.txt" in context.rendered_context
    assert "Previous: We were comparing two policies." in context.rendered_context
    assert (
        "Next: That would help me understand your stance."
        in context.rendered_context
    )
    assert f"Snippet ID: {matching.id}" in context.rendered_context


@pytest.mark.django_db
def test_exemplar_rendered_context_marks_examples_as_style_guidance(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="ULECD040 DIRECTIVES/request_info #2",
        content="have you any data on how people use the services",
        source_uri="elfa-sa://ULECD040.txt#import-key-1",
        source_label="ULECD040.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "ULECD040.txt",
            "previous_sentence": "have you made any user studies",
            "next_sentence": "what do you mean the catalogues",
            "import_key": "import-key-1",
        },
    )

    context = retrieve(
        "latest classroom turn",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )

    assert context.source_statuses["exemplar"] == "success"
    assert "Speech Act examples are style and intent guidance only." in context.rendered_context
    assert "Do not treat them as factual citations or source claims." in context.rendered_context
    assert "have you any data on how people use the services" in context.rendered_context
    assert "Speech Act: DIRECTIVES/request_info" in context.rendered_context
    assert "Source file: ULECD040.txt" in context.rendered_context


@pytest.mark.django_db
def test_exemplar_no_results_message_mentions_no_usable_examples(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Invite exemplar",
        content="Would anyone like to add something?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-3",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-3",
        },
    )

    context = retrieve(
        "show me an example",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="ASSERTIVES",
        speech_act_subtype="inform",
    )

    assert context.items == []
    assert context.source_statuses["exemplar"] == "no-results"
    assert "No usable Speech Act examples were found." in context.rendered_context
    assert "Continue using conversation context only" in context.rendered_context


@pytest.mark.django_db
def test_exemplar_source_returns_same_label_when_query_misses(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    matching = KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/request_info #12",
        content="Could you clarify what you mean by that point?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-1",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "CDIS01A.txt",
            "previous_sentence": "We were comparing two policies.",
            "next_sentence": "That would help me understand your stance.",
            "import_key": "import-key-1",
        },
    )

    context = retrieve(
        "latest classroom turn",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="directives",
        speech_act_subtype="request_info",
    )

    assert context.source_statuses["exemplar"] == "success"
    assert len(context.items) == 1
    assert context.items[0].title == matching.title
    assert context.items[0].metadata["SA_type"] == "DIRECTIVES"
    assert context.items[0].metadata["subtype"] == "request_info"
    assert context.items[0].score == 0.1


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_exemplar_hybrid_retrieval_keeps_label_filter(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    query = "semantic zqxclarification"
    matching = KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/request_info #12",
        content="Unrelated wording that only has an embedding match.",
        source_uri="elfa-sa://CDIS01A.txt#import-key-1",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-1",
        },
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )
    KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/invite #13",
        content="semantic zqxclarification",
        source_uri="elfa-sa://CDIS01A.txt#import-key-2",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-2",
        },
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    context = retrieve(
        query,
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )

    assert context.source_statuses["exemplar"] == "success"
    assert len(context.items) == 1
    assert context.items[0].metadata["knowledge_snippet_id"] == matching.id
    assert context.items[0].metadata["subtype"] == "request_info"
    assert context.items[0].metadata["retrieval_channels"] == ["vector"]
    assert context.items[0].metadata["vector_similarity"] is not None
    assert context.items[0].metadata["vector_rank"] == 1
    assert context.items[0].metadata["embedding_model"] == "fake"


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_vector_semantic_exemplar_can_be_returned_with_label_filter(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    query = "semantic-only exemplar target"
    matching = KnowledgeSnippet.objects.create(
        title="ULECD040 DIRECTIVES/request_info #2",
        content="Text with no overlapping query terms.",
        source_uri="elfa-sa://ULECD040.txt#import-key-1",
        source_label="ULECD040.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "ULECD040.txt",
            "previous_sentence": "have you made any user studies",
            "next_sentence": "what do you mean the catalogues",
            "import_key": "import-key-1",
        },
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    context = retrieve(
        query,
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )

    assert context.source_statuses["exemplar"] == "success"
    assert len(context.items) == 1
    item = context.items[0]
    assert item.metadata["knowledge_snippet_id"] == matching.id
    assert item.metadata["retrieval_channels"] == ["vector"]
    assert item.metadata["keyword_score"] is None
    assert item.metadata["vector_similarity"] is not None
    assert item.metadata["rerank_score"] > 0
    assert item.metadata["global_score"] == item.score
    assert item.metadata["previous_sentence"] == "have you made any user studies"
    assert item.metadata["next_sentence"] == "what do you mean the catalogues"


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_exemplar_source_excludes_non_exemplar_knowledge(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    query = "clarify point"
    KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Could you clarify what you mean by that point?",
        source_uri="course://policy",
        source_label="Course Handbook",
        is_active=True,
        metadata={
            "kind": "course_policy",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "Course Handbook",
            "import_key": "policy",
        },
        embedding=fake_embedding(query),
        embedding_model="fake",
        embedding_dimensions=1536,
    )

    context = retrieve(
        query,
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )

    assert context.items == []
    assert context.source_statuses["exemplar"] == "no-results"


@pytest.mark.django_db
def test_exemplar_source_reports_no_results_when_labels_do_not_match(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="Invite exemplar",
        content="Would anyone like to add something?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-3",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-3",
        },
    )

    context = retrieve(
        "show me an example",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
        speech_act_type="ASSERTIVES",
        speech_act_subtype="inform",
    )

    assert context.items == []
    assert context.source_statuses["exemplar"] == "no-results"


@pytest.mark.django_db
def test_exemplar_source_requires_query_match_without_label_filter(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/request_info #12",
        content="Could you clarify what you mean by that point?",
        source_uri="elfa-sa://CDIS01A.txt#import-key-1",
        source_label="CDIS01A.txt",
        is_active=True,
        metadata={
            "kind": "speech_act_exemplar",
            "SA_type": "DIRECTIVES",
            "subtype": "request_info",
            "file_name": "CDIS01A.txt",
            "import_key": "import-key-1",
        },
    )

    context = retrieve(
        "latest classroom turn",
        session=session,
        user=user,
        sources={"exemplar"},
        top_k=5,
    )

    assert context.items == []
    assert context.source_statuses["exemplar"] == "no-results"


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


@pytest.mark.django_db
def test_persist_turn_retrieval_stores_exemplar_trace_for_agent_turn(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="school")
    processed = append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Could you clarify what kind of data you mean?",
        source="llm",
    )
    rendered_context = (
        "Retrieved information:\n"
        "Speech Act examples are style and intent guidance only.\n"
        "Do not treat them as factual citations or source claims.\n"
        "1. Source: exemplar\n"
        "   Title: ULECD040 DIRECTIVES/request_info #2\n"
        "   URI: elfa-sa://ULECD040.txt#import-key-1\n"
        "   Speech Act: DIRECTIVES/request_info\n"
        "   Source file: ULECD040.txt\n"
        "   Previous: have you made any user studies\n"
        "   Next: what do you mean the catalogues\n"
        "   Snippet ID: 123\n"
        "   Excerpt: have you any data on how people use the services"
    )
    context = RetrievedContext(
        query="Topic: school\nFacilitator instruction: Ask for clarification.",
        requested_sources=["exemplar"],
        source_statuses={"exemplar": "success"},
        items=[
            RetrievedItem(
                source="exemplar",
                title="ULECD040 DIRECTIVES/request_info #2",
                excerpt="have you any data on how people use the services",
                source_uri="elfa-sa://ULECD040.txt#import-key-1",
                source_label="ULECD040.txt",
                score=0.1,
                metadata={
                    "knowledge_snippet_id": 123,
                    "kind": "speech_act_exemplar",
                    "SA_type": "DIRECTIVES",
                    "subtype": "request_info",
                    "file_name": "ULECD040.txt",
                    "previous_sentence": "have you made any user studies",
                    "next_sentence": "what do you mean the catalogues",
                    "import_key": "import-key-1",
                },
            ),
        ],
        rendered_context=rendered_context,
    )

    trace = persist_turn_retrieval(processed.turn, context)

    assert trace.turn == processed.turn
    assert trace.requested_sources == ["exemplar"]
    assert trace.source_statuses == {"exemplar": "success"}
    assert trace.items[0]["source"] == "exemplar"
    assert trace.items[0]["metadata"]["knowledge_snippet_id"] == 123
    assert trace.items[0]["metadata"]["SA_type"] == "DIRECTIVES"
    assert trace.items[0]["metadata"]["subtype"] == "request_info"
    assert trace.items[0]["source_label"] == "ULECD040.txt"
    assert trace.rendered_context == rendered_context


@pytest.mark.django_db
def test_persist_turn_retrieval_safely_suppresses_trace_errors(user, monkeypatch) -> None:
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
        requested_sources=["knowledge"],
        source_statuses={"knowledge": "success"},
        items=[],
        rendered_context="Retrieved information:",
    )

    def fail_persist(turn, context):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("backend.conversation.services.retrieval.persist_turn_retrieval", fail_persist)

    assert persist_turn_retrieval_safely(processed.turn, context) is None
