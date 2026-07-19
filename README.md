# Conversation Agent Starter

Reusable infrastructure (auth, LLM configuration/calls, and a Vue UI) for building a new project.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## Basic Commands

### Running the Vite Dev Server

This app integrates with a Vue frontend located in `vue_frontend`.

##### With Docker
The Vite dev server will automatically run in docker when started with the docker-compose.local.yml configuration.
```sh
cp ./envs/.local/.secrets.example ./envs/.local/.secrets
docker-compose -f docker-compose.local.yml up

# Then initialize the LLM models and API keys
docker-compose -f docker-compose.local.yml run --rm django python manage.py init_llm_seed
```

For a fresh local RAG setup after the containers are built, run:

```sh
make migrate-local
make init-knowledge-local
make init-embeddings-local
```

If you want to import Speech Act knowledge and generate embeddings in one step:

```sh
make init-rag-local
```

### Initializing Speech Act Knowledge Data

Raw corpus files are kept local and are not committed to Git. To seed the Speech Act exemplar knowledge data, place the annotation export at:

```text
Docs & Files/Sample SA annotation/SA_annotations.json
```

Then run:

```sh
make init-knowledge-local
```

This runs Django migrations and imports the annotations into `Exemplar` records. To validate the file without writing database rows, run:

```sh
DRY_RUN=1 make init-knowledge-local
```

To import the annotations and generate missing embeddings in one command, run:

```sh
REFRESH_EMBEDDINGS=1 make init-knowledge-local
```

### Knowledge Embeddings

Knowledge retrieval combines keyword matching with pgvector recall, then applies a deterministic reciprocal-rank rerank. Keyword and vector candidates are merged by `Exemplar`, ranked by stable scores, and written to retrieval traces with `retrieval_channels` metadata such as `["keyword"]`, `["vector"]`, or `["keyword", "vector"]`.

The local and production Postgres images are built from `pgvector/pgvector:pg16`, and migrations enable the pgvector extension plus the `Exemplar.embedding` vector index.

Embedding settings:

- Local/default: `EMBEDDING_PROVIDER=openai`, `EMBEDDING_MODEL=text-embedding-3-small`, and `OPENAI_API_KEY` must be configured before generating embeddings.
- Production: keep `EMBEDDING_PROVIDER=openai`, set `OPENAI_API_KEY` through deployment secrets, and keep `EMBEDDING_MODEL` aligned with stored snippet embeddings.
- Tests: use `EMBEDDING_PROVIDER=fake` for deterministic local vectors without network calls.
- Vector dimension is fixed at 1536 by the Django model and migration. Changing it requires a new migration and embedding backfill.
- Recall tuning: `VECTOR_RECALL_ENABLED`, `HYBRID_KEYWORD_CANDIDATES`, `HYBRID_VECTOR_CANDIDATES`, `HYBRID_RRF_K`, `HYBRID_KEYWORD_WEIGHT`, and `HYBRID_VECTOR_WEIGHT` control hybrid retrieval behavior.

### Text To Speech

The default TTS implementation is configurable. OpenAI remains available for compatibility, and Fish Audio can be enabled with:

```sh
export TTS_PROVIDER="fish"
export FISH_API_KEY="xxxxx"
export FISH_TTS_MODEL="s2-pro"
export FISH_TTS_FORMAT="mp3"
export FISH_TTS_REFERENCE_ID="8ef4a238714b45718ce04243307c57a7"
```

See [Fish Audio TTS Migration README](docs/fish_audio_tts_readme.md) for the changed files, API examples, voice IDs, and local test steps.

Generate missing embeddings after importing knowledge data:

```sh
docker compose -f docker-compose.local.yml run --rm django python manage.py refresh_knowledge_embeddings
```

Equivalent Make target:

```sh
make init-embeddings-local
```

Refresh stale embeddings when the canonical text, provider model, or dimensions changed:

```sh
docker compose -f docker-compose.local.yml run --rm django python manage.py refresh_knowledge_embeddings --stale
```

Equivalent Make target:

```sh
make refresh-embeddings-local
```

Use `--dry-run` to count matching snippets without writing vectors, and `--limit N` to process a bounded batch.

If the embedding provider, query embedding generation, or pgvector recall is unavailable, retrieval falls back to keyword matches. A keyword hit still returns the knowledge source as `success`; only vector-only searches with no keyword candidates report vector recall failure.


### Speaker Profiles (LangMem)

Structured user, agent, and user-agent relationship profiles are stored in LangGraph's PostgresStore (separate store tables in the same Postgres database). This complements the existing UserMemory episodic RAG system.

One-time store setup:

``sh
make setup-speaker-profiles-local
``

Inspect profiles for a user:

``sh
docker compose -f docker-compose.local.yml run --rm django python manage.py dump_speaker_profiles <user_id>
``

The module lives in ackend/conversation/services/speaker_profiles.py. Phase 1 exposes read/seed/extract APIs only; conversation prompt wiring comes later.

### User Long-Term Memory

Long-term memory is stored in the local database as `UserMemory` records and is not committed to Git. After pulling changes that include this feature, run migrations:

```sh
make migrate-local
```

Developers can create or disable user memories from Django admin. The project also includes a lightweight Mem0-style memory flow built on the existing `UserMemory` table. It does not require Mem0, Zep, Letta, Redis, or a separate memory service.

After a user turn is saved, the backend can asynchronously ask the configured LLM for candidate long-term memories. The LLM only proposes candidates; backend rules decide what is saved. The backend filters invalid memory types, low-confidence candidates, temporary topics, generated CEFR sample text, sensitive information, duplicates, and agent-only claims.

Stable structured profile fields are synchronized without the LLM:

- `preferred_name`
- `major`
- `cefr_level`

Set `USER_MEMORY_EXTRACTION_ENABLED=false` to disable LLM-based conversation memory extraction. Profile sync can still run because it does not call the LLM.

Memory retrieval combines keyword matching with pgvector recall, then writes returned memory metadata into `TurnRetrieval`. If vector recall is needed for newly created memories, refresh memory embeddings after creating records:

```sh
docker compose -f docker-compose.local.yml run --rm django python manage.py refresh_user_memory_embeddings --stale --skip-errors
```

Use `--dry-run` to count matching memory records without writing vectors, and `--limit N` to process a bounded batch.

##### From the console
Alternatively you, may run the Vite dev server directly from the project directory:
```sh
cd vue_frontend
npm install
npm run dev
````

### Scene background images

Scene masters are PNG files in `vue_frontend/scenes-src/`. The app serves optimized WebP assets from `vue_frontend/public/scenes/` (full-size display + `.thumb.webp` for the setup picker).

When you **add or replace** a scene master:

1. Put the PNG in `vue_frontend/scenes-src/` (e.g. `new-scene.png`).
2. Regenerate WebPs:

```sh
make optimize-scenes
```

Or from the frontend folder:

```sh
cd vue_frontend
npm run optimize:scenes
```

3. Register the scene in `vue_frontend/src/lib/conversationScenes.ts` with `url` and `thumbUrl` pointing at the new `.webp` / `.thumb.webp` files.
4. Commit the master PNG, the generated WebPs, and the TypeScript change.

You do **not** need to run this for normal `npm run dev` or production builds — those use the committed WebPs in `public/scenes/`.

### Partner thumbnail images

Partner select on Discussion Setup uses static WebP thumbs (not Live2D). Masters are PNG files named by character id in `vue_frontend/partner-thumbs-src/` (e.g. `haru.png`). Optimized assets are served from `vue_frontend/public/partner-thumbs/`.

When you **add or replace** a partner thumb:

1. Put the PNG in `vue_frontend/partner-thumbs-src/` using the character id as the filename.
2. Regenerate WebPs:

```sh
make optimize-partner-thumbs
```

Or from the frontend folder:

```sh
cd vue_frontend
npm run optimize:partner-thumbs
```

Characters without a matching WebP fall back to `public/partner-thumbs/_placeholder_girl1.webp`. Commit the master PNG and the generated WebP.

For more information, refer to the [Vue3 Vite Django Cookiecutter project](https://github.com/ilikerobots/cookiecutter-vue-django).



### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      $ python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    $ mypy backend

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    $ coverage run -m pytest
    $ coverage html
    $ open htmlcov/index.html

#### Running tests with pytest

    $ pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd backend
celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd backend
celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd backend
celery -A config.celery_app worker -B -l info
```

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. For that reason local SMTP server [Mailpit](https://github.com/axllent/mailpit) with a web interface is available as docker container.

Container mailpit will start automatically when you will run all docker containers.
Please check [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally-docker.html) for more details how to start all containers.

With Mailpit running, to view messages that are sent by your application, open your browser and go to `http://127.0.0.1:8025`

### Sentry

Sentry is an error logging aggregator service. You can sign up for a free account at <https://sentry.io/signup/?code=cookiecutter> or download and host it yourself.
The system is set up with reasonable defaults, including 404 logging and integration with the WSGI application.

You must set the DSN url in production.

## Deployment

The following details how to deploy this application.

### Heroku

See detailed [cookiecutter-django Heroku documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-on-heroku.html).

### Vue

For production deployment, the Vue frontend must be built into static resources, which will be served
using the same Django staticfiles strategy as the rest of your site.

If you are using the production Docker configuration, this will be performed automatically when the images are built.

Otherwise, you must build the static assets yourself as part of your build and deploy process, sometime before the
`collectstatic` management command is run. The static assets may be built by running `npm run build` from within the
`vue_frontend` directory. The resulting files will be placed into the `backend/static/vue` directory
and are handled subsequently as standard static assets.

Note the setting `VUE_FRONTEND_USE_DEV_SERVER` dictates whether your Django app will be expecting to serve Vue assets
from the Vite Dev Server or from a static build.  This setting defaults to the same as `DEBUG`, but can be modified as
needed.
If you wish to build static Vue assets on the local Docker configuration, you may run:
`docker-compose -f local.yml run vite vite build`

For more information, refer to the [Vue3 Vite Django Cookiecutter project](https://github.com/ilikerobots/cookiecutter-vue-django).

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).
