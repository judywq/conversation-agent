#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.local.yml}"
DJANGO_SERVICE="${DJANGO_SERVICE:-django}"
DEFAULT_ANNOTATIONS_PATH="Docs & Files/Sample SA annotation/SA_annotations.json"
ANNOTATIONS_PATH="${1:-${SA_ANNOTATIONS_PATH:-$DEFAULT_ANNOTATIONS_PATH}}"

usage() {
  cat <<'EOF'
Usage:
  scripts/init_knowledge.sh [path/to/SA_annotations.json]

Environment:
  SA_ANNOTATIONS_PATH  Optional path to SA_annotations.json when no argument is passed.
  COMPOSE_FILE          Docker compose file to use. Defaults to docker-compose.local.yml.
  DJANGO_SERVICE        Django service name. Defaults to django.
  DRY_RUN=1             Parse the data without writing Exemplar rows.
  REFRESH_EMBEDDINGS=1  Generate missing embeddings after import. Requires
                        OPENAI_API_KEY unless EMBEDDING_PROVIDER=fake.

Examples:
  scripts/init_knowledge.sh
  scripts/init_knowledge.sh "Docs & Files/Sample SA annotation/SA_annotations.json"
  DRY_RUN=1 scripts/init_knowledge.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$ANNOTATIONS_PATH" = /* ]]; then
  HOST_ANNOTATIONS_PATH="$ANNOTATIONS_PATH"
else
  HOST_ANNOTATIONS_PATH="$ROOT_DIR/$ANNOTATIONS_PATH"
fi

if [[ ! -f "$HOST_ANNOTATIONS_PATH" ]]; then
  echo "ERROR: annotation file not found:" >&2
  echo "  $HOST_ANNOTATIONS_PATH" >&2
  echo >&2
  usage >&2
  exit 1
fi

cd "$ROOT_DIR"

CONTAINER_ANNOTATIONS_PATH="/tmp/sa_annotations.json"
VOLUME_SPEC="$HOST_ANNOTATIONS_PATH:$CONTAINER_ANNOTATIONS_PATH:ro"

echo "Running migrations with $COMPOSE_FILE..."
docker compose -f "$COMPOSE_FILE" run --rm "$DJANGO_SERVICE" python manage.py migrate

IMPORT_ARGS=(python manage.py import_speech_act_exemplars "$CONTAINER_ANNOTATIONS_PATH")
if [[ "${DRY_RUN:-}" == "1" || "${DRY_RUN:-}" == "true" ]]; then
  IMPORT_ARGS+=(--dry-run)
fi

echo "Importing Speech Act exemplars from $CONTAINER_ANNOTATIONS_PATH..."
docker compose -f "$COMPOSE_FILE" run --rm -v "$VOLUME_SPEC" "$DJANGO_SERVICE" "${IMPORT_ARGS[@]}"

if [[ "${DRY_RUN:-}" == "1" || "${DRY_RUN:-}" == "true" ]]; then
  exit 0
fi

if [[ "${REFRESH_EMBEDDINGS:-}" == "1" || "${REFRESH_EMBEDDINGS:-}" == "true" ]]; then
  echo "Generating missing Exemplar embeddings..."
  docker compose -f "$COMPOSE_FILE" run --rm "$DJANGO_SERVICE" \
    python manage.py refresh_exemplar_embeddings
fi
