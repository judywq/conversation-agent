import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.services import agent as agent_service
from backend.conversation.services.agent import _avoid_question_ending_when_not_request
from backend.conversation.services.agent import _build_agent_retrieval_context
from backend.conversation.services.agent import _enforce_directive_target_name
from backend.conversation.services.agent import _limit_to_three_sentences
from backend.conversation.services.agent import _normalize_directive_question_punctuation
from backend.conversation.services.agent import generate_agent_utterance
from backend.conversation.services.agent import generate_agent_utterance_with_retrieval
from backend.conversation.services.agent import resolve_agent_retrieval_sources
from backend.conversation.services.retrieval import RetrievedContext
from backend.conversation.services.turn_processor import append_turn


def test_enforce_directive_target_name_prepends_when_missing():
    out = _enforce_directive_target_name(
        "Could you explain your idea a bit more?",
        speech_act_type="DIRECTIVES",
        target_display_name="Alex",
    )
    assert out.endswith(", Alex?")


def test_enforce_directive_target_name_noop_when_present_case_insensitive():
    out = _enforce_directive_target_name(
        "alex, could you explain your idea a bit more?",
        speech_act_type="DIRECTIVES",
        target_display_name="Alex",
    )
    assert out == "alex, could you explain your idea a bit more?"


def test_enforce_directive_target_name_noop_for_non_directives():
    out = _enforce_directive_target_name(
        "I agree with that.",
        speech_act_type="EXPRESSIVES",
        target_display_name="Alex",
    )
    assert out == "I agree with that."


def test_avoid_question_ending_converts_non_directives_to_period():
    out = _avoid_question_ending_when_not_request(
        "I agree with that?",
        speech_act_type="ASSERTIVES",
        speech_act_subtype="opinion",
    )
    assert out == "I agree with that."


def test_avoid_question_ending_keeps_request_like_directives():
    out = _avoid_question_ending_when_not_request(
        "What do you think?",
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )
    assert out == "What do you think?"


def test_limit_to_three_sentences_truncates():
    out = _limit_to_three_sentences("One. Two! Three? Four. Five.")
    assert out == "One. Two! Three?"


def test_normalize_directive_question_punctuation_converts_named_period_to_question():
    utterance = (
        "Um, I take the school bus because it is easy and I can relax, "
        "I mean sometimes I even think what if buses had fun screens for learning. "
        "Do you like taking the school bus, Judy."
    )
    out = _normalize_directive_question_punctuation(
        utterance,
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
        target_display_name="Judy",
    )
    assert out.endswith("Do you like taking the school bus, Judy?")


def test_enforce_directive_target_name_appends_to_period_ended_interrogative():
    out = _enforce_directive_target_name(
        "Do you like taking the school bus.",
        speech_act_type="DIRECTIVES",
        target_display_name="Judy",
    )
    assert out.endswith(", Judy?")


def _make_session_with_agent(user):
    session = ConversationSession.objects.create(user=user, topic="Climate policy")
    agent = AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        display_name="Alex",
        personality={},
        traits={"proficiency_level": "B2"},
    )
    return session, agent


@pytest.mark.django_db
def test_build_agent_retrieval_context_routes_web_search_to_web_only(user, monkeypatch):
    session, _agent = _make_session_with_agent(user)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="We should ground this in recent evidence.",
        source="text",
    )
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["query"] = query
        captured["session"] = session
        captured["user"] = user
        captured["sources"] = sources
        captured["top_k"] = top_k
        captured["speech_act_type"] = speech_act_type
        captured["speech_act_subtype"] = speech_act_subtype
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"web": "success"},
            items=[],
            rendered_context="Retrieved information:\n1. Source: web",
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    context = _build_agent_retrieval_context(
        session,
        {
            "retrieval_requirement": "web_search",
            "content_requirement": "Use a recent policy example.",
        },
    )

    assert captured["sources"] == {"web"}
    assert captured["session"] == session
    assert captured["user"] == user
    assert captured["top_k"] == 5
    assert captured["speech_act_type"] == ""
    assert captured["speech_act_subtype"] == ""
    assert "Topic: Climate policy" in captured["query"]
    assert "Facilitator instruction: Use a recent policy example." in captured["query"]
    assert "Latest turn: We should ground this in recent evidence." in captured["query"]
    assert context.rendered_context == "Retrieved information:\n1. Source: web"


@pytest.mark.django_db
def test_build_agent_retrieval_context_routes_memory_to_unified_sources(user, monkeypatch):
    session, _agent = _make_session_with_agent(user)
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["sources"] = sources
        captured["speech_act_type"] = speech_act_type
        captured["speech_act_subtype"] = speech_act_subtype
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"memory": "not-configured", "session": "no-results", "knowledge": "no-results"},
            items=[],
            rendered_context=(
                "No usable retrieved information was found. Continue using conversation context only; "
                "do not invent citations."
            ),
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    _build_agent_retrieval_context(
        session,
        {
            "retrieval_requirement": "memory",
            "content_requirement": "Recall earlier preferences.",
        },
    )

    assert captured["sources"] == {"memory", "session", "knowledge"}
    assert captured["speech_act_type"] == ""
    assert captured["speech_act_subtype"] == ""


@pytest.mark.django_db
def test_build_agent_retrieval_context_always_retrieves_exemplar_when_facilitator_says_none(
    user,
    monkeypatch,
):
    session, _agent = _make_session_with_agent(user)
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["sources"] = sources
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"exemplar": "success"},
            items=[],
            rendered_context="Retrieved information:",
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    context = _build_agent_retrieval_context(
        session,
        {
            "retrieval_requirement": "none",
            "content_requirement": "Keep it conversational.",
        },
    )

    assert captured["sources"] == {"exemplar"}
    assert "exemplar" in context.source_statuses


@pytest.mark.django_db
def test_build_agent_retrieval_context_fact_checker_web_when_facilitator_says_none(
    user,
    monkeypatch,
):
    session, agent = _make_session_with_agent(user)
    agent.personality = {"persona_name": "Fact Checker"}
    agent.save(update_fields=["personality"])
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["sources"] = sources
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"exemplar": "success", "web": "success"},
            items=[],
            rendered_context="Retrieved information:",
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    _build_agent_retrieval_context(
        session,
        {
            "retrieval_requirement": "none",
            "type": "ASSERTIVES",
            "subtype": "inform",
            "content_requirement": "Verify the claim with a source.",
        },
        agent=agent,
    )

    assert captured["sources"] == {"exemplar", "web"}


@pytest.mark.parametrize(
    "retrieval_requirement",
    ["exemplar", "speech_act_exemplar", "speech act exemplar"],
)
@pytest.mark.django_db
def test_build_agent_retrieval_context_routes_exemplar_labels(
    user,
    monkeypatch,
    retrieval_requirement,
):
    session, _agent = _make_session_with_agent(user)
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["query"] = query
        captured["sources"] = sources
        captured["top_k"] = top_k
        captured["speech_act_type"] = speech_act_type
        captured["speech_act_subtype"] = speech_act_subtype
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"exemplar": "success"},
            items=[],
            rendered_context="Retrieved information:\n1. Source: exemplar",
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    context = _build_agent_retrieval_context(
        session,
        {
            "retrieval_requirement": retrieval_requirement,
            "type": "DIRECTIVES",
            "subtype": "request_info",
            "content_requirement": "Use a speech act example.",
        },
    )

    assert captured["sources"] == {"exemplar"}
    assert captured["top_k"] == 5
    assert captured["speech_act_type"] == "DIRECTIVES"
    assert captured["speech_act_subtype"] == "request_info"
    assert "Topic: Climate policy" in captured["query"]
    assert context.rendered_context == "Retrieved information:\n1. Source: exemplar"


@pytest.mark.django_db
def test_generate_agent_utterance_injects_unified_retrieved_context(user, monkeypatch):
    session, agent = _make_session_with_agent(user)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Can you support that with a source?",
        source="text",
    )
    monkeypatch.setattr(
        agent_service,
        "_build_agent_retrieval_context",
        lambda session, facilitator_plan: RetrievedContext(
            query="query",
            requested_sources=["web", "knowledge"],
            source_statuses={"web": "success", "knowledge": "success"},
            items=[],
            rendered_context="Retrieved information:\n1. Source: knowledge\n   Title: Course handbook",
        ),
    )
    captured = {}

    class FakeResult:
        content = "I think the course handbook supports that."

    class FakeLLM:
        def invoke(self, messages):
            captured["system_prompt"] = messages[0].content
            return FakeResult()

    monkeypatch.setattr(agent_service, "get_default_chat_llm", lambda: FakeLLM())

    utterance = generate_agent_utterance(
        session,
        agent=agent,
        facilitator_plan={
            "retrieval_requirement": "web_search",
            "type": "ASSERTIVES",
            "subtype": "inform",
            "content_requirement": "Use evidence.",
        },
    )

    assert utterance == "I think the course handbook supports that."
    assert "Retrieved information:\n1. Source: knowledge\n   Title: Course handbook" in captured["system_prompt"]
    assert "Retrieved web context" not in captured["system_prompt"]
    assert "today only web search is implemented" not in captured["system_prompt"]


@pytest.mark.django_db
def test_generate_agent_utterance_injects_speech_act_exemplar_guidance(user, monkeypatch):
    session, agent = _make_session_with_agent(user)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I am not sure what evidence you mean.",
        source="text",
    )
    snippet = KnowledgeSnippet.objects.create(
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
    captured = {}

    class FakeResult:
        content = "Could you say what data you mean, Alex?"

    class FakeLLM:
        def invoke(self, messages):
            captured["system_prompt"] = messages[0].content
            return FakeResult()

    monkeypatch.setattr(agent_service, "get_default_chat_llm", lambda: FakeLLM())

    generated = generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan={
            "retrieval_requirement": "speech act exemplar",
            "type": "DIRECTIVES",
            "subtype": "request_info",
            "target": "user",
            "content_requirement": "Ask for clarification about the evidence.",
        },
    )

    prompt = captured["system_prompt"]
    assert generated.retrieval_context.source_statuses["exemplar"] == "success"
    assert generated.retrieval_context.items[0].metadata["knowledge_snippet_id"] == snippet.id
    assert "have you any data on how people use the services" in prompt
    assert "Speech Act: DIRECTIVES/request_info" in prompt
    assert "Source file: ULECD040.txt" in prompt
    assert "Previous: have you made any user studies" in prompt
    assert "Next: what do you mean the catalogues" in prompt
    assert f"Snippet ID: {snippet.id}" in prompt
    assert "Speech Act examples are style and intent guidance only." in prompt
    assert "Speech Act examples in retrieved context are style and intent guidance only." in prompt
    assert "Do not cite Speech Act examples as evidence" in prompt


@pytest.mark.django_db
def test_generate_agent_utterance_with_retrieval_returns_context_for_persistence(user, monkeypatch):
    session, agent = _make_session_with_agent(user)
    retrieval_context = RetrievedContext(
        query="query",
        requested_sources=["memory", "session"],
        source_statuses={"memory": "not-configured", "session": "no-results"},
        items=[],
        rendered_context=(
            "No usable retrieved information was found. Continue using conversation context only; "
            "do not invent citations."
        ),
    )
    monkeypatch.setattr(
        agent_service,
        "_build_agent_retrieval_context",
        lambda session, facilitator_plan: retrieval_context,
    )

    class FakeResult:
        content = "Let's continue from what we already discussed."

    class FakeLLM:
        def invoke(self, messages):
            return FakeResult()

    monkeypatch.setattr(agent_service, "get_default_chat_llm", lambda: FakeLLM())

    generated = generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan={
            "retrieval_requirement": "memory",
            "type": "ASSERTIVES",
            "subtype": "inform",
            "content_requirement": "Use context.",
        },
    )

    assert generated.utterance == "Let's continue from what we already discussed."
    assert generated.utterance_tts == "Let's continue from what we already discussed."
    assert generated.retrieval_context == retrieval_context


def _patch_minimal_pipeline(monkeypatch, llm_content: str) -> None:
    monkeypatch.setattr(
        agent_service,
        "_build_agent_retrieval_context",
        lambda session, facilitator_plan: RetrievedContext(
            query="query",
            requested_sources=[],
            source_statuses={},
            items=[],
            rendered_context="",
        ),
    )

    class FakeResult:
        content = llm_content

    class FakeLLM:
        def invoke(self, messages):
            return FakeResult()

    monkeypatch.setattr(agent_service, "get_default_chat_llm", lambda: FakeLLM())


@pytest.mark.django_db
def test_generate_agent_utterance_keeps_valid_audio_tag_in_tts_strips_for_display(
    user,
    monkeypatch,
):
    session, agent = _make_session_with_agent(user)
    _patch_minimal_pipeline(monkeypatch, "[reflective] Hmm, I'm not sure about that.")

    generated = generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan={
            "type": "ASSERTIVES",
            "subtype": "opinion",
            "content_requirement": "",
        },
    )

    assert generated.utterance == "Hmm, I'm not sure about that."
    assert generated.utterance_tts == "[reflective] Hmm, I'm not sure about that."


@pytest.mark.django_db
def test_generate_agent_utterance_strips_unknown_bracket_content_from_both(
    user,
    monkeypatch,
):
    session, agent = _make_session_with_agent(user)
    _patch_minimal_pipeline(monkeypatch, "[meta] I agree (as agent_2). Let's continue.")

    generated = generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan={
            "type": "ASSERTIVES",
            "subtype": "opinion",
            "content_requirement": "",
        },
    )

    for field in (generated.utterance, generated.utterance_tts):
        assert "meta" not in field
        assert "agent_2" not in field
        assert "I agree" in field
        assert "Let's continue" in field


@pytest.mark.django_db
def test_generate_agent_utterance_mixed_tags_display_tag_free_tts_only_valid(
    user,
    monkeypatch,
):
    session, agent = _make_session_with_agent(user)
    _patch_minimal_pipeline(
        monkeypatch,
        "[deliberate] The data is clear. [meta] (as agent_2) [quietly] Trust me.",
    )

    generated = generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan={
            "type": "ASSERTIVES",
            "subtype": "inform",
            "content_requirement": "",
        },
    )

    assert "[" not in generated.utterance
    assert "(" not in generated.utterance
    assert "The data is clear." in generated.utterance
    assert "Trust me." in generated.utterance

    assert "[deliberate]" in generated.utterance_tts
    assert "[quietly]" in generated.utterance_tts
    assert "meta" not in generated.utterance_tts
    assert "agent_2" not in generated.utterance_tts


@pytest.mark.django_db
def test_resolve_agent_retrieval_sources_includes_news_only_for_assertives_inform(user):
    session = ConversationSession.objects.create(
        user=user,
        topic="Topic",
        discussion_article_ids=[101, 102],
    )

    inform_sources = resolve_agent_retrieval_sources(
        {"type": "ASSERTIVES", "subtype": "inform"},
        session=session,
    )
    opinion_sources = resolve_agent_retrieval_sources(
        {"type": "ASSERTIVES", "subtype": "opinion"},
        session=session,
    )
    directive_sources = resolve_agent_retrieval_sources(
        {"type": "DIRECTIVES", "subtype": "request_info"},
        session=session,
    )

    assert "news" in inform_sources
    assert "news" not in opinion_sources
    assert "news" not in directive_sources


@pytest.mark.django_db
def test_build_agent_retrieval_context_includes_news_for_assertives_inform(user, monkeypatch):
    session, _agent = _make_session_with_agent(user)
    session.discussion_article_ids = [201]
    session.save(update_fields=["discussion_article_ids"])
    captured = {}

    def fake_retrieve(  # noqa: PLR0913
        query,
        *,
        session,
        user,
        sources,
        top_k,
        speech_act_type,
        speech_act_subtype,
    ):
        captured["sources"] = sources
        return RetrievedContext(
            query=query,
            requested_sources=sorted(sources),
            source_statuses={"news": "success"},
            items=[],
            rendered_context="Retrieved information:\n1. Source: news",
        )

    monkeypatch.setattr(agent_service, "retrieve", fake_retrieve)

    _build_agent_retrieval_context(
        session,
        {
            "type": "ASSERTIVES",
            "subtype": "inform",
            "retrieval_requirement": "none",
        },
    )

    assert "news" in captured["sources"]
