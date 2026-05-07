from pathlib import Path

import pytest

from backend.conversation.models import KnowledgeSnippet
from backend.conversation.services.speech_act_exemplars import EXEMPLAR_KIND
from backend.conversation.services.speech_act_exemplars import build_import_key
from backend.conversation.services.speech_act_exemplars import import_speech_act_annotations
from backend.conversation.services.speech_act_exemplars import normalize_annotation_row


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sa_annotations_sample.json"


def test_normalize_annotation_row_maps_required_fields() -> None:
    row = {
        "file_name": "CDIS01A.txt",
        "sentence": "  I would have   one question.  ",
        "context": {
            "previous_sentence": "  Thank you.\n",
            "next_sentence": "\tYes please.  ",
        },
        "SA_type": "directives",
        "subtype": "REQUEST_INFO",
    }

    normalized = normalize_annotation_row(row, row_number=7)

    assert normalized is not None
    assert normalized.file_name == "CDIS01A.txt"
    assert normalized.sentence == "I would have one question."
    assert normalized.previous_sentence == "Thank you."
    assert normalized.next_sentence == "Yes please."
    assert normalized.sa_type == "DIRECTIVES"
    assert normalized.subtype == "request_info"
    assert normalized.row_number == 7


def test_normalize_annotation_row_rejects_missing_sentence() -> None:
    row = {
        "file_name": "BROKEN.txt",
        "context": {"previous_sentence": None, "next_sentence": None},
        "SA_type": "ASSERTIVES",
        "subtype": "inform",
    }

    assert normalize_annotation_row(row, row_number=1) is None


def test_normalize_annotation_row_rejects_non_dict_context() -> None:
    row = {
        "file_name": "CDIS01A.txt",
        "sentence": "I would have one question.",
        "context": "invalid",
        "SA_type": "DIRECTIVES",
        "subtype": "request_info",
    }

    assert normalize_annotation_row(row, row_number=2) is None


def test_build_import_key_includes_context_and_label() -> None:
    baseline = build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yeah.",
        sa_type="EXPRESSIVES",
        subtype="acknowledge",
        previous_sentence="Do you agree?",
        next_sentence="Good.",
    )

    assert len(baseline) == 64
    assert baseline != build_import_key(
        file_name="ALT01A.txt",
        sentence="Yeah.",
        sa_type="EXPRESSIVES",
        subtype="acknowledge",
        previous_sentence="Do you agree?",
        next_sentence="Good.",
    )
    assert baseline != build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yes.",
        sa_type="EXPRESSIVES",
        subtype="acknowledge",
        previous_sentence="Do you agree?",
        next_sentence="Good.",
    )
    assert baseline != build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yeah.",
        sa_type="ASSERTIVES",
        subtype="acknowledge",
        previous_sentence="Do you agree?",
        next_sentence="Good.",
    )
    assert baseline != build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yeah.",
        sa_type="EXPRESSIVES",
        subtype="agree",
        previous_sentence="Do you agree?",
        next_sentence="Good.",
    )
    assert baseline != build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yeah.",
        sa_type="EXPRESSIVES",
        subtype="acknowledge",
        previous_sentence="Is January correct?",
        next_sentence="Good.",
    )
    assert baseline != build_import_key(
        file_name="CDIS01A.txt",
        sentence="Yeah.",
        sa_type="EXPRESSIVES",
        subtype="acknowledge",
        previous_sentence="Do you agree?",
        next_sentence="January.",
    )


@pytest.mark.django_db
def test_import_speech_act_annotations_creates_distinct_snippets() -> None:
    summary = import_speech_act_annotations(FIXTURE_PATH)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert summary.dry_run is False
    assert KnowledgeSnippet.objects.count() == 3

    snippet = KnowledgeSnippet.objects.get(
        content="I wonder whether there are any questions you'd like to ask.",
    )
    assert snippet.title == "CDIS01A DIRECTIVES/invite #1"
    assert snippet.source_label == "CDIS01A.txt"
    assert snippet.source_uri.startswith("elfa-sa://CDIS01A.txt#")
    assert snippet.is_active is True
    assert snippet.metadata["kind"] == EXEMPLAR_KIND
    assert snippet.metadata["SA_type"] == "DIRECTIVES"
    assert snippet.metadata["subtype"] == "invite"
    assert snippet.metadata["file_name"] == "CDIS01A.txt"
    assert snippet.metadata["previous_sentence"] is None
    assert snippet.metadata["next_sentence"] == "Nobody."
    assert snippet.metadata["annotation_source"] == "SA_annotations.json"
    assert snippet.metadata["import_batch"] == "basecamp-speech-act-annotations"
    assert snippet.metadata["row_number"] == 1
    assert len(snippet.metadata["import_key"]) == 64

    assert KnowledgeSnippet.objects.filter(content="Yeah.").count() == 2


@pytest.mark.django_db
def test_import_speech_act_annotations_is_idempotent() -> None:
    first = import_speech_act_annotations(FIXTURE_PATH)
    second = import_speech_act_annotations(FIXTURE_PATH)

    assert first.created == 3
    assert second.created == 0
    assert second.skipped == 4
    assert second.invalid == 1
    assert KnowledgeSnippet.objects.count() == 3


@pytest.mark.django_db
def test_import_speech_act_annotations_ignores_non_exemplar_import_keys() -> None:
    import_key = build_import_key(
        file_name="CDIS01A.txt",
        sentence="I wonder whether there are any questions you'd like to ask.",
        sa_type="DIRECTIVES",
        subtype="invite",
        previous_sentence=None,
        next_sentence="Nobody.",
    )
    KnowledgeSnippet.objects.create(
        title="Unrelated snippet",
        content="Unrelated content",
        source_uri="course://policy",
        source_label="Course Handbook",
        metadata={"import_key": import_key},
    )

    summary = import_speech_act_annotations(FIXTURE_PATH)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert KnowledgeSnippet.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


@pytest.mark.django_db
def test_import_speech_act_annotations_ignores_other_annotation_sources() -> None:
    import_key = build_import_key(
        file_name="CDIS01A.txt",
        sentence="I wonder whether there are any questions you'd like to ask.",
        sa_type="DIRECTIVES",
        subtype="invite",
        previous_sentence=None,
        next_sentence="Nobody.",
    )
    KnowledgeSnippet.objects.create(
        title="Other source exemplar",
        content="Unrelated content",
        source_uri="elfa-sa://CDIS01A.txt#other",
        source_label="CDIS01A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "annotation_source": "other_annotations.json",
            "import_key": import_key,
        },
    )

    summary = import_speech_act_annotations(FIXTURE_PATH)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert KnowledgeSnippet.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 4


@pytest.mark.django_db
def test_import_speech_act_annotations_ignores_other_kinds() -> None:
    import_key = build_import_key(
        file_name="CDIS01A.txt",
        sentence="I wonder whether there are any questions you'd like to ask.",
        sa_type="DIRECTIVES",
        subtype="invite",
        previous_sentence=None,
        next_sentence="Nobody.",
    )
    KnowledgeSnippet.objects.create(
        title="Other kind snippet",
        content="Unrelated content",
        source_uri="course://policy",
        source_label="Course Handbook",
        metadata={
            "kind": "course_policy",
            "annotation_source": "SA_annotations.json",
            "import_key": import_key,
        },
    )

    summary = import_speech_act_annotations(FIXTURE_PATH)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert KnowledgeSnippet.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


@pytest.mark.django_db
def test_import_speech_act_annotations_dry_run_does_not_write() -> None:
    summary = import_speech_act_annotations(FIXTURE_PATH, dry_run=True)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert summary.dry_run is True
    assert KnowledgeSnippet.objects.count() == 0
