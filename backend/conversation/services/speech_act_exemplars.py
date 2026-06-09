from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.conversation.models import Exemplar
from backend.conversation.services.facilitator import ALLOWED_SA

EXEMPLAR_KIND = "speech_act_exemplar"
ANNOTATION_SOURCE = "SA_annotations.json"

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SpeechActAnnotation:
    file_name: str
    sentence: str
    previous_sentence: str | None
    next_sentence: str | None
    sa_type: str
    subtype: str
    row_number: int


@dataclass(frozen=True)
class ImportSummary:
    created: int
    skipped: int
    invalid: int
    dry_run: bool


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _WHITESPACE_RE.sub(" ", value).strip()
    return normalized or None


def build_import_key(  # noqa: PLR0913
    *,
    file_name: str,
    sentence: str,
    sa_type: str,
    subtype: str,
    previous_sentence: str | None,
    next_sentence: str | None,
) -> str:
    payload = {
        "SA_type": sa_type,
        "file_name": file_name,
        "next_sentence": next_sentence,
        "previous_sentence": previous_sentence,
        "sentence": sentence,
        "subtype": subtype,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_annotation_row(
    raw: Any,
    *,
    row_number: int,
) -> SpeechActAnnotation | None:
    if not isinstance(raw, dict):
        return None

    context = raw.get("context")
    if not isinstance(context, dict):
        return None

    file_name = _normalize_text(raw.get("file_name"))
    sentence = _normalize_text(raw.get("sentence"))
    sa_type_raw = _normalize_text(raw.get("SA_type"))
    subtype_raw = _normalize_text(raw.get("subtype"))
    if not file_name or not sentence or not sa_type_raw or not subtype_raw:
        return None

    sa_type = sa_type_raw.upper()
    subtype = subtype_raw.lower()
    allowed_subtypes = ALLOWED_SA.get(sa_type)
    if allowed_subtypes is None or subtype not in allowed_subtypes:
        return None

    return SpeechActAnnotation(
        file_name=file_name,
        sentence=sentence,
        previous_sentence=_normalize_text(context.get("previous_sentence")),
        next_sentence=_normalize_text(context.get("next_sentence")),
        sa_type=sa_type,
        subtype=subtype,
        row_number=row_number,
    )


def import_speech_act_annotations(
    path: str | Path,
    *,
    dry_run: bool = False,
    import_batch: str = "basecamp-speech-act-annotations",
) -> ImportSummary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return ImportSummary(created=0, skipped=0, invalid=1, dry_run=dry_run)

    existing_import_keys = {
        import_key
        for import_key in Exemplar.objects.filter(
            metadata__kind=EXEMPLAR_KIND,
        ).values_list("metadata__import_key", flat=True)
        if isinstance(import_key, str) and import_key
    }

    created = 0
    skipped = 0
    invalid = 0
    seen_import_keys = set(existing_import_keys)

    for row_number, raw in enumerate(data, start=1):
        annotation = normalize_annotation_row(raw, row_number=row_number)
        if annotation is None:
            invalid += 1
            continue

        import_key = build_import_key(
            file_name=annotation.file_name,
            sentence=annotation.sentence,
            sa_type=annotation.sa_type,
            subtype=annotation.subtype,
            previous_sentence=annotation.previous_sentence,
            next_sentence=annotation.next_sentence,
        )
        if import_key in seen_import_keys:
            skipped += 1
            continue

        seen_import_keys.add(import_key)
        created += 1
        if dry_run:
            continue

        title = (
            f"{Path(annotation.file_name).stem} "
            f"{annotation.sa_type}/{annotation.subtype} "
            f"#{annotation.row_number}"
        )
        Exemplar.objects.create(
            title=title,
            content=annotation.sentence,
            source_uri=f"elfa-sa://{annotation.file_name}#{import_key[:12]}",
            source_label=annotation.file_name,
            is_active=True,
            metadata={
                "kind": EXEMPLAR_KIND,
                "SA_type": annotation.sa_type,
                "subtype": annotation.subtype,
                "file_name": annotation.file_name,
                "previous_sentence": annotation.previous_sentence,
                "next_sentence": annotation.next_sentence,
                "annotation_source": ANNOTATION_SOURCE,
                "import_batch": import_batch,
                "import_key": import_key,
                "row_number": annotation.row_number,
            },
        )

    return ImportSummary(
        created=created,
        skipped=skipped,
        invalid=invalid,
        dry_run=dry_run,
    )
