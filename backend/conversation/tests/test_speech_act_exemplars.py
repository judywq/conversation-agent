# ruff: noqa: PLR2004

from io import StringIO
from pathlib import Path

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory

from backend.conversation.admin import ExemplarKindListFilter
from backend.conversation.admin import ExemplarAdmin
from backend.conversation.admin import SourceFileListFilter
from backend.conversation.admin import SpeechActSubtypeListFilter
from backend.conversation.admin import SpeechActTypeListFilter
from backend.conversation.models import Exemplar
from backend.conversation.services import speech_act_exemplars

EXEMPLAR_KIND = speech_act_exemplars.EXEMPLAR_KIND
build_import_key = speech_act_exemplars.build_import_key
import_speech_act_annotations = speech_act_exemplars.import_speech_act_annotations
normalize_annotation_row = speech_act_exemplars.normalize_annotation_row


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
    assert Exemplar.objects.count() == 3

    snippet = Exemplar.objects.get(
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

    assert Exemplar.objects.filter(content="Yeah.").count() == 2


@pytest.mark.django_db
def test_import_speech_act_annotations_is_idempotent() -> None:
    first = import_speech_act_annotations(FIXTURE_PATH)
    second = import_speech_act_annotations(FIXTURE_PATH)

    assert first.created == 3
    assert second.created == 0
    assert second.skipped == 4
    assert second.invalid == 1
    assert Exemplar.objects.count() == 3


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
    Exemplar.objects.create(
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
    assert Exemplar.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


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
    Exemplar.objects.create(
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

    assert summary.created == 2
    assert summary.skipped == 2
    assert summary.invalid == 1
    assert Exemplar.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


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
    Exemplar.objects.create(
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
    assert Exemplar.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


@pytest.mark.django_db
def test_import_speech_act_annotations_dry_run_does_not_write() -> None:
    summary = import_speech_act_annotations(FIXTURE_PATH, dry_run=True)

    assert summary.created == 3
    assert summary.skipped == 1
    assert summary.invalid == 1
    assert summary.dry_run is True
    assert Exemplar.objects.count() == 0


@pytest.mark.django_db
def test_import_speech_act_exemplars_command_writes_summary() -> None:
    stdout = StringIO()

    call_command("import_speech_act_exemplars", str(FIXTURE_PATH), stdout=stdout)

    assert stdout.getvalue().strip() == "created=3 skipped=1 invalid=1 dry_run=False"
    assert Exemplar.objects.count() == 3


@pytest.mark.django_db
def test_import_speech_act_exemplars_command_dry_run_writes_nothing() -> None:
    stdout = StringIO()

    call_command(
        "import_speech_act_exemplars",
        str(FIXTURE_PATH),
        "--dry-run",
        stdout=stdout,
    )

    assert stdout.getvalue().strip() == "created=3 skipped=1 invalid=1 dry_run=True"
    assert Exemplar.objects.count() == 0


@pytest.mark.django_db
def test_import_command_reports_existing_exemplar_duplicates() -> None:
    import_key = build_import_key(
        file_name="CDIS01A.txt",
        sentence="I wonder whether there are any questions you'd like to ask.",
        sa_type="DIRECTIVES",
        subtype="invite",
        previous_sentence=None,
        next_sentence="Nobody.",
    )
    Exemplar.objects.create(
        title="Existing exemplar",
        content="Existing exemplar content",
        source_uri="elfa-sa://CDIS01A.txt#other",
        source_label="CDIS01A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "annotation_source": "other_annotations.json",
            "import_key": import_key,
        },
    )
    stdout = StringIO()

    call_command("import_speech_act_exemplars", str(FIXTURE_PATH), stdout=stdout)

    assert stdout.getvalue().strip() == "created=2 skipped=2 invalid=1 dry_run=False"
    assert Exemplar.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 3


@pytest.mark.django_db
def test_import_command_dry_run_reports_existing_exemplar_duplicates() -> None:
    import_key = build_import_key(
        file_name="CDIS01A.txt",
        sentence="I wonder whether there are any questions you'd like to ask.",
        sa_type="DIRECTIVES",
        subtype="invite",
        previous_sentence=None,
        next_sentence="Nobody.",
    )
    Exemplar.objects.create(
        title="Existing exemplar",
        content="Existing exemplar content",
        source_uri="elfa-sa://CDIS01A.txt#other",
        source_label="CDIS01A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "annotation_source": "other_annotations.json",
            "import_key": import_key,
        },
    )
    stdout = StringIO()

    call_command(
        "import_speech_act_exemplars",
        str(FIXTURE_PATH),
        "--dry-run",
        stdout=stdout,
    )

    assert stdout.getvalue().strip() == "created=2 skipped=2 invalid=1 dry_run=True"
    assert Exemplar.objects.filter(metadata__kind=EXEMPLAR_KIND).count() == 1


@pytest.mark.django_db
def test_exemplar_admin_config_exposes_exemplar_metadata() -> None:
    model_admin = ExemplarAdmin(Exemplar, admin.site)
    snippet = Exemplar.objects.create(
        title="Invite exemplar",
        content="Would anyone like to add something?",
        source_uri="elfa-sa://CDIS01A.txt#1",
        source_label="CDIS01A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "file_name": "CDIS01A.txt",
        },
    )

    required_list_display = {
        "id",
        "title",
        "content_excerpt",
        "metadata_kind",
        "metadata_sa_type",
        "metadata_subtype",
        "metadata_file_name",
        "source_label",
        "source_uri",
        "is_active",
        "updated_at",
    }
    assert required_list_display.issubset(set(model_admin.list_display))
    long_content = (
        "This exemplar content is intentionally long so the admin "
        "list view shows a concise preview instead of the full body."
    )
    excerpt = model_admin.content_excerpt(
        Exemplar(
            content=long_content,
        ),
    )
    assert excerpt.startswith(
        "This exemplar content is intentionally long so the admin list view",
    )
    assert excerpt.endswith("...")
    assert len(excerpt) < len(long_content)
    assert model_admin.metadata_kind(snippet) == EXEMPLAR_KIND
    assert model_admin.metadata_sa_type(snippet) == "DIRECTIVES"
    assert model_admin.metadata_subtype(snippet) == "invite"
    assert model_admin.metadata_file_name(snippet) == "CDIS01A.txt"
    required_search_fields = {
        "title",
        "content",
        "source_label",
        "source_uri",
        "metadata__kind",
        "metadata__SA_type",
        "metadata__subtype",
        "metadata__file_name",
    }
    assert required_search_fields.issubset(set(model_admin.search_fields))

    required_actions = {
        "enable_selected_exemplars",
        "disable_selected_exemplars",
    }
    assert required_actions.issubset(set(model_admin.actions))

    filter_classes = [
        item for item in model_admin.list_filter if isinstance(item, type)
    ]
    assert "is_active" in model_admin.list_filter
    assert "source_label" in model_admin.list_filter
    assert ExemplarKindListFilter in filter_classes
    assert SpeechActTypeListFilter in filter_classes
    assert SpeechActSubtypeListFilter in filter_classes
    assert SourceFileListFilter in filter_classes


@pytest.mark.django_db
def test_exemplar_admin_metadata_filters_match_expected_snippets() -> None:
    Exemplar.objects.create(
        title="Invite exemplar",
        content="Would anyone like to add something?",
        source_uri="elfa-sa://CDIS01A.txt#1",
        source_label="CDIS01A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "file_name": "CDIS01A.txt",
        },
    )
    Exemplar.objects.create(
        title="Acknowledge exemplar",
        content="Yeah.",
        source_uri="elfa-sa://CDIS02A.txt#2",
        source_label="CDIS02A.txt",
        metadata={
            "kind": EXEMPLAR_KIND,
            "SA_type": "EXPRESSIVES",
            "subtype": "acknowledge",
            "file_name": "CDIS02A.txt",
        },
    )
    Exemplar.objects.create(
        title="Course policy",
        content="Policy content",
        source_uri="course://policy",
        source_label="Course Handbook",
        metadata={"kind": "course_policy"},
    )
    Exemplar.objects.create(
        title="None metadata values",
        content="Ignored lookup values",
        source_uri="course://none",
        source_label="Misc",
        metadata={
            "kind": None,
            "SA_type": "",
            "subtype": None,
            "file_name": "",
        },
    )
    Exemplar.objects.create(
        title="Empty metadata",
        content="Ignored by lookups",
        source_uri="course://empty",
        source_label="Misc",
        metadata={},
    )
    Exemplar.objects.create(
        title="Non-dict metadata",
        content="Ignored by lookups",
        source_uri="course://invalid",
        source_label="Misc",
        metadata=["unexpected"],
    )

    model_admin = ExemplarAdmin(Exemplar, admin.site)
    request_factory = RequestFactory()

    kind_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_kind": EXEMPLAR_KIND},
    )
    kind_filter = ExemplarKindListFilter(
        kind_request,
        kind_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    kind_results = kind_filter.queryset(
        kind_request,
        Exemplar.objects.order_by("title"),
    )
    assert list(kind_results.values_list("title", flat=True)) == [
        "Acknowledge exemplar",
        "Invite exemplar",
    ]

    sa_type_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_sa_type": "DIRECTIVES"},
    )
    sa_type_filter = SpeechActTypeListFilter(
        sa_type_request,
        sa_type_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    sa_type_results = sa_type_filter.queryset(
        sa_type_request,
        Exemplar.objects.all(),
    )
    assert list(sa_type_results.values_list("title", flat=True)) == ["Invite exemplar"]

    subtype_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_subtype": "acknowledge"},
    )
    subtype_filter = SpeechActSubtypeListFilter(
        subtype_request,
        subtype_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    subtype_results = subtype_filter.queryset(
        subtype_request,
        Exemplar.objects.all(),
    )
    assert list(subtype_results.values_list("title", flat=True)) == [
        "Acknowledge exemplar",
    ]

    source_file_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_file_name": "CDIS02A.txt"},
    )
    source_file_filter = SourceFileListFilter(
        source_file_request,
        source_file_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    source_file_results = source_file_filter.queryset(
        source_file_request,
        Exemplar.objects.all(),
    )
    assert list(source_file_results.values_list("title", flat=True)) == [
        "Acknowledge exemplar",
    ]

    kind_lookups = dict(
        ExemplarKindListFilter(
            kind_request,
            kind_request.GET.copy(),
            Exemplar,
            model_admin,
        ).lookups(kind_request, model_admin),
    )
    sa_type_lookups = dict(
        SpeechActTypeListFilter(
            sa_type_request,
            sa_type_request.GET.copy(),
            Exemplar,
            model_admin,
        ).lookups(
            sa_type_request,
            model_admin,
        ),
    )
    subtype_lookups = dict(
        SpeechActSubtypeListFilter(
            subtype_request,
            subtype_request.GET.copy(),
            Exemplar,
            model_admin,
        ).lookups(
            subtype_request,
            model_admin,
        ),
    )
    source_file_lookups = dict(
        SourceFileListFilter(
            source_file_request,
            source_file_request.GET.copy(),
            Exemplar,
            model_admin,
        ).lookups(
            source_file_request,
            model_admin,
        ),
    )

    assert set(kind_lookups) == {EXEMPLAR_KIND}
    assert set(sa_type_lookups) == {"DIRECTIVES", "EXPRESSIVES"}
    assert set(subtype_lookups) == {"acknowledge", "invite"}
    assert set(source_file_lookups) == {"CDIS01A.txt", "CDIS02A.txt"}

    invalid_kind_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_kind": "course_policy"},
    )
    invalid_kind_filter = ExemplarKindListFilter(
        invalid_kind_request,
        invalid_kind_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    assert not invalid_kind_filter.queryset(
        invalid_kind_request,
        Exemplar.objects.all(),
    ).exists()

    missing_sa_type_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_sa_type": "COMMISSIVES"},
    )
    missing_sa_type_filter = SpeechActTypeListFilter(
        missing_sa_type_request,
        missing_sa_type_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    assert not missing_sa_type_filter.queryset(
        missing_sa_type_request,
        Exemplar.objects.all(),
    ).exists()

    missing_subtype_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_subtype": "nonexistent"},
    )
    missing_subtype_filter = SpeechActSubtypeListFilter(
        missing_subtype_request,
        missing_subtype_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    assert not missing_subtype_filter.queryset(
        missing_subtype_request,
        Exemplar.objects.all(),
    ).exists()

    missing_source_file_request = request_factory.get(
        "/admin/conversation/Exemplar/",
        {"metadata_file_name": "UNKNOWN.txt"},
    )
    missing_source_file_filter = SourceFileListFilter(
        missing_source_file_request,
        missing_source_file_request.GET.copy(),
        Exemplar,
        model_admin,
    )
    assert not missing_source_file_filter.queryset(
        missing_source_file_request,
        Exemplar.objects.all(),
    ).exists()


@pytest.mark.django_db
def test_exemplar_admin_bulk_actions_toggle_is_active() -> None:
    disabled_snippet = Exemplar.objects.create(
        title="Disabled exemplar",
        content="Please continue.",
        source_uri="elfa-sa://CDIS01A.txt#3",
        source_label="CDIS01A.txt",
        is_active=False,
        metadata={"kind": EXEMPLAR_KIND},
    )
    enabled_snippet = Exemplar.objects.create(
        title="Enabled exemplar",
        content="Yeah.",
        source_uri="elfa-sa://CDIS02A.txt#4",
        source_label="CDIS02A.txt",
        is_active=True,
        metadata={"kind": EXEMPLAR_KIND},
    )
    model_admin = ExemplarAdmin(Exemplar, admin.site)

    def ignore_message_user(request, message):
        return None

    model_admin.message_user = ignore_message_user

    request = RequestFactory().post("/admin/conversation/Exemplar/")
    model_admin.enable_selected_exemplars(
        request,
        Exemplar.objects.filter(pk=disabled_snippet.pk),
    )
    disabled_snippet.refresh_from_db()
    assert disabled_snippet.is_active is True

    model_admin.disable_selected_exemplars(
        request,
        Exemplar.objects.filter(pk=enabled_snippet.pk),
    )
    enabled_snippet.refresh_from_db()
    assert enabled_snippet.is_active is False
