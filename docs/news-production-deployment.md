# News Module Production Deployment

This document explains how to deploy the news ingestion module on a remote
server.

## What Must Be Deployed

The news module runs inside the existing Django project. The required code is
already part of the repository:

```text
backend/news/
config/settings/base.py
config/urls.py
docs/news-ingestion.md
docs/news-topic-taxonomy.md
```

OpenSpec change files are not required for production runtime.

## Required Services

The production Docker Compose file already defines the services needed by the
news module:

```text
django
postgres
redis
celeryworker
celerybeat
```

The news module depends on:

- `django` for migrations, admin, and the read API.
- `postgres` for `NewsArticle` and `NewsClassification` records.
- `redis` as the Celery broker/result backend.
- `celeryworker` to execute news sync and classification tasks.
- `celerybeat` to schedule periodic sync and classification tasks.

## Required External Service

Miniflux is not deployed by this Django project. It must be deployed separately
or already available from another server.

Django only needs to reach the Miniflux API URL configured by
`MINIFLUX_BASE_URL`.

Recommended production setup:

```text
RSS feeds -> Miniflux -> Django sync task -> GPT classification -> Django API
```

## Production Environment Variables

On the server, create the real production secrets file:

```bash
cp .envs/.production/.secrets.example .envs/.production/.secrets
```

Then edit:

```bash
nano .envs/.production/.secrets
```

Add the existing production secrets required by the project, plus the news
module settings:

```text
MINIFLUX_BASE_URL=https://your-miniflux-domain.example.com
MINIFLUX_API_TOKEN=your-miniflux-api-token
MINIFLUX_TIMEOUT_SEC=15.0

OPENAI_API_KEY=your-openai-api-key
```

Use `MINIFLUX_API_TOKEN` in production. `MINIFLUX_USERNAME` and
`MINIFLUX_PASSWORD` are supported, but they are better kept for local testing.

Do not commit `.envs/.production/.secrets` to GitHub.

## Deploy From GitHub

On the remote server:

```bash
git clone git@github.com:judywq/conversation-agent.git
cd conversation-agent
```

If the repository already exists:

```bash
cd conversation-agent
git pull origin main
```

Build and start the production services:

```bash
docker compose -f docker-compose.production.yml up -d --build
```

The production Django start script already runs:

```text
collectstatic
migrate
```

So the `news.0001_initial` migration should be applied automatically when the
`django` service starts.

## Start Only News-Related Runtime Services

If the main stack is already running and you only need the news background
workers:

```bash
docker compose -f docker-compose.production.yml up -d celeryworker celerybeat
```

Check status:

```bash
docker compose -f docker-compose.production.yml ps
```

Check logs:

```bash
docker compose -f docker-compose.production.yml logs celeryworker
docker compose -f docker-compose.production.yml logs celerybeat
```

## Schedule

The default schedule is configured in Django settings:

```text
sync_miniflux_news: every 1 hour
classify_unclassified_news: every 30 minutes
```

`celerybeat` triggers these jobs. `celeryworker` executes them.

## Manual Verification

After deployment, run a manual sync first:

```bash
docker compose -f docker-compose.production.yml exec django \
  python manage.py sync_miniflux_news --limit 20
```

Expected output:

```text
Miniflux sync complete: created=<number> updated=<number> duplicate_urls=<number>
```

Check that articles exist:

```bash
docker compose -f docker-compose.production.yml exec django \
  python manage.py shell -c "from backend.news.models import NewsArticle; print(NewsArticle.objects.count())"
```

Check that the API returns classified articles after classification has run:

```text
GET /api/news/classified-articles/?category=technology-ai
```

The endpoint requires authentication.

## Miniflux Feed Setup

RSS feeds configured in local Miniflux do not automatically move to the remote
server.

Use one of these approaches:

- Recreate feeds manually in the remote Miniflux UI.
- Export OPML from local Miniflux and import it into remote Miniflux.

Keep Miniflux feed categories for source organization. The student-facing
learning taxonomy is owned by Django.

## Common Problems

### Django Cannot Connect To Miniflux

Check:

```bash
docker compose -f docker-compose.production.yml exec django \
  python manage.py shell -c "from backend.news.miniflux import MinifluxClient; print(len(MinifluxClient.from_settings().fetch_recent_entries(limit=1).get('entries', [])))"
```

If this fails, verify:

- `MINIFLUX_BASE_URL`
- `MINIFLUX_API_TOKEN`
- server firewall rules
- whether Miniflux is reachable from the Django container

### Classification Does Not Run

Check:

- `OPENAI_API_KEY` exists in `.envs/.production/.secrets`.
- `celeryworker` is running.
- `celerybeat` is running.
- the server can reach the GPT API from inside the Django/Celery containers.

### Articles Exist But API Returns Empty Results

This usually means articles are synchronized but not successfully classified.

Check classifications:

```bash
docker compose -f docker-compose.production.yml exec django \
  python manage.py shell -c "from backend.news.models import NewsClassification; print(NewsClassification.objects.values('status').order_by('status').distinct())"
```

Only successful and suitable classifications are returned by the read API.
