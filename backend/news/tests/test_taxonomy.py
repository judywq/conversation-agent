import pytest

from backend.news.taxonomy import MAIN_CATEGORY_SLUGS
from backend.news.taxonomy import TAXONOMY_VERSION
from backend.news.taxonomy import get_category
from backend.news.taxonomy import get_subtopic


def test_main_category_slugs_are_stable():
    assert TAXONOMY_VERSION == "2026-06-03"
    assert MAIN_CATEGORY_SLUGS == (
        "society-lifestyle",
        "technology-ai",
        "education-learning",
        "environment-sustainability",
        "business-work-economy",
        "health-psychology",
        "culture-media",
        "global-issues-ethics",
    )


def test_get_category_rejects_unknown_slug():
    with pytest.raises(ValueError, match="Unknown news category"):
        get_category("unknown")


def test_get_subtopic_rejects_subtopic_outside_category():
    with pytest.raises(ValueError, match="Unknown news subtopic"):
        get_subtopic("technology-ai", "burnout")
