import pytest

from backend.conversation.services.web_search import build_scenario_knowledge_query
from backend.conversation.services.web_search import web_search_context_is_usable


def test_build_scenario_knowledge_query_includes_scenario():
    query = build_scenario_knowledge_query(
        category_name="Technology & AI",
        subtopic_name="AI teachers",
        scenario="Should schools adopt AI tutors?",
    )
    assert "Technology & AI / AI teachers" in query
    assert "Should schools adopt AI tutors?" in query


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Summary: Useful facts.", True),
        ("(Web search is disabled; proceed without verified external facts.)", False),
        ("(Web search failed; proceed without verified external facts.)", False),
        ("", False),
    ],
)
def test_web_search_context_is_usable(text, expected):
    assert web_search_context_is_usable(text) is expected
