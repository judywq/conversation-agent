# Replace the % with the desired environment, e.g. `make run-local` for local environment
# or `make run-production` for production environment

# Show configs
config-%:
	docker compose -f docker-compose.$*.yml config

# Enter logs
logs-%:
	docker compose -f docker-compose.$*.yml logs -f

# Build images
build-%:
	docker compose -f docker-compose.$*.yml build

# Run containers
start-%:
	docker compose -f docker-compose.$*.yml up -d

# Run local environment with debug mode (will wait for debugger)
start-local-debug:
	docker compose -f docker-compose.local.yml -f docker-compose.debug.yml up -d

# Stop containers
stop-%:
	docker compose -f docker-compose.$*.yml down

# Restart containers
restart-%:
	docker compose -f docker-compose.$*.yml restart


# Restart traefik containers
rt-%:
	docker compose -f docker-compose.$*.yml down traefik
	docker compose -f docker-compose.$*.yml up -d traefik
# Restart django containers
rd-%:
	docker compose -f docker-compose.$*.yml down django
	docker compose -f docker-compose.$*.yml up -d django

# Restart celery containers
rc-%:
	docker compose -f docker-compose.$*.yml down celeryworker
	docker compose -f docker-compose.$*.yml up -d celeryworker

# Full restart containers
frestart-%:
	$(MAKE) stop-$*
	$(MAKE) start-$*

# Stop containers and remove all volumes
rm-vol-%:
	docker compose -f docker-compose.$*.yml down -v

# Enter shell
sh-%:
	docker compose -f docker-compose.$*.yml exec -it django /bin/bash

# Enter django shell
djshell-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py shell_plus

# List files in media directory
list-media-files-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py list_media_files

# Delete files in media directory older than 30 days
delete-media-files-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py delete_media_files --days 30

# Create a superuser
csu-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py createsuperuser

# Make migrations (local only)
mm:
	docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations

# Migrate database
migrate-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py migrate

# Seed LLM models + API keys from config/settings/base.py (INIT_LLM_MODELS, INIT_API_KEYS)
init-llm-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py init_llm_seed

# Migrate local DB and import local Speech Act knowledge exemplars
init-knowledge-local:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/init_knowledge.ps1
else
	./scripts/init_knowledge.sh
endif

# Generate missing Exemplar embeddings
init-embeddings-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py refresh_exemplar_embeddings

# Refresh stale Exemplar embeddings after text/model changes
refresh-embeddings-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py refresh_exemplar_embeddings --stale

# Migrate, import local Speech Act knowledge, and generate embeddings
init-rag-%:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "$$env:REFRESH_EMBEDDINGS='1'; $$env:COMPOSE_FILE='docker-compose.$*.yml'; ./scripts/init_knowledge.ps1"
else
	REFRESH_EMBEDDINGS=1 COMPOSE_FILE=docker-compose.$*.yml ./scripts/init_knowledge.sh
endif

pytest:
	docker compose -f docker-compose.local.yml run --rm django pytest

# Pre-commit
pc:
	pipenv run pre-commit run --all-files

# Remove static volume
rm-static-vol:
	docker volume rm conversation_agent_production_django_static

sync-news-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py sync_miniflux_news --limit 100

# One-time LangMem PostgresStore table setup for speaker profiles
setup-speaker-profiles-%:
	docker compose -f docker-compose.$*.yml run --rm django python manage.py setup_langmem_store

# Regenerate scene WebP display + thumb assets from vue_frontend/scenes-src/
optimize-scenes:
	cd vue_frontend && npm run optimize:scenes

