# News Ingestion

This project uses Miniflux as the RSS aggregation service and Django as the
learning-domain news store.

## Responsibility Split

```text
RSS sources -> Miniflux -> Django news sync -> LLM classification -> learning flows
```

Miniflux owns:

- RSS subscriptions
- feed refresh
- feed fetch errors
- feed-level categories
- entry normalization from RSS/Atom

Django owns:

- article storage for learning
- duplicate prevention by Miniflux entry id and normalized URL
- the project learning taxonomy
- LLM-based pre-classification
- read APIs for already-classified articles

Do not treat Miniflux categories as the final student-facing taxonomy. Miniflux
categories organize sources. Django categories and subtopics organize learning.

## Environment Settings

Configure these values through `.envs/` or deployment environment variables.
Do not commit production secrets.

```text
MINIFLUX_BASE_URL=http://localhost:8081
MINIFLUX_API_TOKEN=
MINIFLUX_USERNAME=
MINIFLUX_PASSWORD=
MINIFLUX_TIMEOUT_SEC=15.0
NEWS_SYNC_BATCH_SIZE=100
NEWS_CLASSIFICATION_BATCH_SIZE=25
```

Prefer `MINIFLUX_API_TOKEN` for production. Local development may use
`MINIFLUX_USERNAME` and `MINIFLUX_PASSWORD` when testing against a local
Miniflux instance.

## Local Manual Sync

Run a one-off sync:

```bash
docker compose -f docker-compose.local.yml run --rm django \
  python manage.py sync_miniflux_news --limit 50
```

The sync stores title, summary, source, URL, publication metadata, and trace
metadata. It does not scrape or store full article text.

## Automatic Schedule

The default Celery Beat schedule runs two background jobs:

- `backend.news.tasks.sync_miniflux_news` every 1 hour.
- `backend.news.tasks.classify_unclassified_news` every 30 minutes.

Students do not trigger these jobs directly. Learning flows read only articles
that have already been synchronized and classified in Django.

## Classification

The classifier reads stored article metadata and asks the configured LLM for
strict JSON using the taxonomy in `backend.news.taxonomy`. Valid classification
results are stored in `NewsClassification`.

Malformed LLM output, unknown categories, unknown subtopics, and provider errors
are recorded as failed classifications. Failed classifications are not returned
by the default learning article API.

## Read API

Authenticated clients can query suitable classified articles:

```text
GET /api/news/classified-articles/?category=technology-ai
GET /api/news/classified-articles/?category=technology-ai&subtopic=ai-teachers
```

The API returns only articles already stored and already classified in Django.
It does not trigger live Miniflux synchronization or live LLM classification.
