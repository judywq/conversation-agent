# ruff: noqa: ERA001, E501
"""Base settings to build other settings files upon."""

import ssl
from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# backend/
APPS_DIR = BASE_DIR / "backend"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "Asia/Tokyo"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
LANGUAGES = [
    ("en", _("English")),
]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

DOMAIN_NAME = env.str("DJANGO_DOMAIN_NAME", default="localhost:8000")

# Conversation
# ------------------------------------------------------------------------------
# For quick testing, you can override via env var CONVERSATION_AGENT_COUNT.
CONVERSATION_AGENT_COUNT = env.int("CONVERSATION_AGENT_COUNT", default=3)
# For quick testing, you can override via env var CONVERSATION_MAX_TURNS.
CONVERSATION_MAX_TURNS = env.int("CONVERSATION_MAX_TURNS", default=20)
CONVERSATION_MAX_EXTENSION_TURNS = env.int("CONVERSATION_MAX_EXTENSION_TURNS", default=4)
# Short-term memory window: how many recent turn_index groups are put into LLM prompts.
CONVERSATION_SHORT_TERM_TURNS = env.int("CONVERSATION_SHORT_TERM_TURNS", default=3)
# When True, prompts get the entire transcript and CONVERSATION_SHORT_TERM_TURNS is ignored.
CONVERSATION_FULL_CONTEXT = env.bool("CONVERSATION_FULL_CONTEXT", default=False)
# Experiment runs only: an LLM answers on the learner's behalf instead of waiting for the
# browser. MUST stay False anywhere real participants use the system.
SIMULATED_STUDENT_ENABLED = env.bool("SIMULATED_STUDENT_ENABLED", default=False)
# Agent audio is dead weight in an unattended run; only consulted while simulating.
SIMULATED_STUDENT_SKIP_TTS = env.bool("SIMULATED_STUDENT_SKIP_TTS", default=True)
AGENT_UTTERANCE_DUPLICATE_THRESHOLD = env.float("AGENT_UTTERANCE_DUPLICATE_THRESHOLD", default=0.75)
AGENT_UTTERANCE_DUPLICATE_MIN_TOKENS = env.int("AGENT_UTTERANCE_DUPLICATE_MIN_TOKENS", default=4)
AGENT_UTTERANCE_DUPLICATE_RECENT_LIMIT = env.int("AGENT_UTTERANCE_DUPLICATE_RECENT_LIMIT", default=20)

# Facilitator web_search retrieval through OpenAI Responses API.
WEB_SEARCH_ENABLED = env.bool("WEB_SEARCH_ENABLED", default=False)
WEB_SEARCH_MODEL = env.str("WEB_SEARCH_MODEL", default="gpt-5")
WEB_SEARCH_API_URL = env.str("WEB_SEARCH_API_URL", default="")
WEB_SEARCH_API_KEY = env.str("WEB_SEARCH_API_KEY", default="")
WEB_SEARCH_TIMEOUT_SEC = env.float("WEB_SEARCH_TIMEOUT_SEC", default=30.0)
USER_MEMORY_EXTRACTION_ENABLED = env.bool(
    "USER_MEMORY_EXTRACTION_ENABLED",
    default=True,
)

# LangMem speaker profiles (user / agent / relationship)
SPEAKER_PROFILES_ENABLED = env.bool("SPEAKER_PROFILES_ENABLED", default=True)
LANGMEM_ENABLED = env.bool("LANGMEM_ENABLED", default=True)
LANGMEM_PROFILE_EXTRACTION_ENABLED = env.bool("LANGMEM_PROFILE_EXTRACTION_ENABLED", default=True)
WEB_SEARCH_PROVIDER = env.str("WEB_SEARCH_PROVIDER", default="openai")
TAVILY_API = env.str("TAVILY_API", default="")

# News ingestion from Miniflux.
MINIFLUX_BASE_URL = env.str("MINIFLUX_BASE_URL", default="")
MINIFLUX_API_TOKEN = env.str("MINIFLUX_API_TOKEN", default="")
MINIFLUX_USERNAME = env.str("MINIFLUX_USERNAME", default="")
MINIFLUX_PASSWORD = env.str("MINIFLUX_PASSWORD", default="")
MINIFLUX_TIMEOUT_SEC = env.float("MINIFLUX_TIMEOUT_SEC", default=15.0)
NEWS_SYNC_BATCH_SIZE = env.int("NEWS_SYNC_BATCH_SIZE", default=100)
NEWS_CLASSIFICATION_BATCH_SIZE = env.int("NEWS_CLASSIFICATION_BATCH_SIZE", default=25)

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# Channels
# ------------------------------------------------------------------------------
ASGI_APPLICATION = "config.asgi.application"
# TODO: change to RedisChannelLayer in production
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("redis", 6379)],
        },
    },
}

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.humanize", # Handy template tags
    "django.contrib.admin",
    "django.forms",
    "channels",
]
THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
    "allauth.socialaccount",
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "backend.users",
    "backend.llm_caller",
    "backend.conversation",
    "backend.news",
    # Your stuff: custom apps go here
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# dj-rest-auth
SITE_ID = 1

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "backend.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "backend.users.context_processors.allauth_settings",
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
# CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# Set the session cookie age for debugging purposes
# SESSION_COOKIE_AGE = 10

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Judy Wang""", "judy.wang@aoni.waseda.jp")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "channels": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
REDIS_SSL = REDIS_URL.startswith("rediss://")

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE} if REDIS_SSL else None
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_TIME_LIMIT = 60 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "sync-miniflux-news-hourly": {
        "task": "backend.news.tasks.sync_miniflux_news",
        "schedule": 60 * 60,
    },
    "classify-news-half-hourly": {
        "task": "backend.news.tasks.classify_unclassified_news",
        "schedule": 30 * 60,
    },
}
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT = True
# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_AUTHENTICATION_METHOD = "email"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "backend.users.adapters.AccountAdapter"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True  # use email verification by code
# ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
# https://docs.allauth.org/en/latest/account/forms.html
ACCOUNT_FORMS = {"signup": "backend.users.forms.UserSignupForm"}
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "backend.users.adapters.SocialAccountAdapter"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_FORMS = {"signup": "backend.users.forms.UserSocialSignupForm"}
# https://docs.allauth.org/en/latest/headless/configuration.html


# dj-rest-auth
# https://stackoverflow.com/a/78795012/1938012
# https://dj-rest-auth.readthedocs.io/en/latest/configuration.html
REST_AUTH = {
    "LOGIN_SERIALIZER": "backend.users.api.serializers.CustomLoginSerializer",
    "REGISTER_SERIALIZER": "backend.users.api.serializers.CustomRegisterSerializer",
    "PASSWORD_CHANGE_SERIALIZER": "backend.users.api.serializers.CustomPasswordChangeSerializer",
    "TOKEN_SERIALIZER": "backend.users.api.serializers.TokenSerializer",
    "USER_DETAILS_SERIALIZER": "backend.users.api.serializers.CustomUserDetailsSerializer",
    # Fix dj-rest-auth weird issue https://github.com/iMerica/dj-rest-auth/issues/494#issuecomment-2058652960
    "PASSWORD_RESET_USE_SITES_DOMAIN": True,
    "OLD_PASSWORD_FIELD_ENABLED": True,
}

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.api_exceptions.custom_exception_handler",
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
# Include /media/ so the Vue dev server can fetch TTS audio into Web Audio (TalkingHead lip-sync).
CORS_URLS_REGEX = r"^(/api/|/media/).*$"
CORS_ALLOW_CREDENTIALS = True

# By Default swagger ui is available only to admin user(s). You can change permission classes to change that
# See more configuration options at https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS = {
    "TITLE": "ATG API",
    "DESCRIPTION": "Documentation of API endpoints of ATG",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SCHEMA_PATH_PREFIX": "/api/",
}

# Vue
# -------------------------------------------------------------------------------
VUE_FRONTEND_USE_DEV_SERVER = DEBUG
VUE_FRONTEND_DEV_SERVER_URL = "http://localhost:5173"
VUE_FRONTEND_DEV_SERVER_PATH = "src/"
VUE_FRONTEND_STATIC_DIR = "vue"
VUE_FRONTEND_USE_TYPESCRIPT = False
# Your stuff...
# ------------------------------------------------------------------------------

# https://platform.openai.com/docs/guides/structured-outputs#supported-models
OPENAI_JSON_SCHEMA_MODELS = [
    "o1",
    "o1-2024-12-17",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
]

# Reasoning models, we might need to remove the <think> tags from the response
REASONING_LLM_MODELS = [
    "o1",
    "o1-2024-12-17",
    "o1-mini-2024-09-12",
    "o3-mini-2025-01-31",
    "deepseek-r1-distill-llama-70b",
    "deepseek-reasoner",
]

# OpenAI reasoning models only support temperature of 1
FIXED_TEMPERATURE_LLM_MODELS = [
    "o1",
    "o1-2024-12-17",
    "o1-mini-2024-09-12",
    "o3-mini-2025-01-31",
]

# Init LLM Models
# ------------------------------------------------------------------------------
INIT_LLM_MODELS = [
    {
        "llm_type": "openai",
        "name": "gpt-5.5-2026-04-23",
        "display_name": "GPT-5.5",
        "is_default": True,
        "is_active": True,
        "order": 12,
    },
    {
        "llm_type": "anthropic",
        "name": "claude-sonnet-4-7",
        "display_name": "Claude 4.7 Sonnet",
        "is_default": False,
        "is_active": True,
        "order": 70,
    },
    {
        "llm_type": "openai",
        "name": "gpt-5-search-api",
        "display_name": "GPT-5 Search API",
        "is_default": False,
        "is_active": True,
        "order": 13,
    },
]

# Text-game seed data (genres + prompt templates) was removed.

OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
TTS_PROVIDER = env.str("TTS_PROVIDER", default="openai")
OPENAI_TTS_MODEL = env.str("OPENAI_TTS_MODEL", default="gpt-4o-mini-tts")
OPENAI_TTS_VOICE = env.str("OPENAI_TTS_VOICE", default="alloy")
FISH_API_KEY = env.str("FISH_API_KEY", default="")
FISH_TTS_MODEL = env.str("FISH_TTS_MODEL", default="s2-pro")
FISH_TTS_REFERENCE_ID = env.str("FISH_TTS_REFERENCE_ID", default="")
FISH_TTS_FORMAT = env.str("FISH_TTS_FORMAT", default="mp3")
FISH_TTS_CONNECT_TIMEOUT_SEC = env.float("FISH_TTS_CONNECT_TIMEOUT_SEC", default=15.0)
FISH_TTS_TIMEOUT_SEC = env.float("FISH_TTS_TIMEOUT_SEC", default=90.0)
ELEVENLABS_API_KEY = env.str("ELEVENLABS_API_KEY", default="")
ELEVENLABS_MODEL_ID = env.str("ELEVENLABS_MODEL_ID", default="eleven_v3")
ELEVENLABS_OUTPUT_FORMAT = env.str("ELEVENLABS_OUTPUT_FORMAT", default="mp3_44100_128")
ELEVENLABS_DEFAULT_VOICE_ID = env.str("ELEVENLABS_DEFAULT_VOICE_ID", default="")
ELEVENLABS_TTS_CONNECT_TIMEOUT_SEC = env.float("ELEVENLABS_TTS_CONNECT_TIMEOUT_SEC", default=15.0)
ELEVENLABS_TTS_TIMEOUT_SEC = env.float("ELEVENLABS_TTS_TIMEOUT_SEC", default=90.0)
CEFR_TTS_MAX_WORKERS = env.int("CEFR_TTS_MAX_WORKERS", default=0)
EMBEDDING_PROVIDER = env.str("EMBEDDING_PROVIDER", default="openai")
EMBEDDING_MODEL = env.str("EMBEDDING_MODEL", default="text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=50)
EMBEDDING_OPENAI_TIMEOUT_SEC = env.float("EMBEDDING_OPENAI_TIMEOUT_SEC", default=30.0)
VECTOR_RECALL_ENABLED = env.bool("VECTOR_RECALL_ENABLED", default=True)
HYBRID_KEYWORD_CANDIDATES = env.int("HYBRID_KEYWORD_CANDIDATES", default=20)
HYBRID_VECTOR_CANDIDATES = env.int("HYBRID_VECTOR_CANDIDATES", default=20)
HYBRID_RRF_K = env.int("HYBRID_RRF_K", default=60)
HYBRID_KEYWORD_WEIGHT = env.float("HYBRID_KEYWORD_WEIGHT", default=1.0)
HYBRID_VECTOR_WEIGHT = env.float("HYBRID_VECTOR_WEIGHT", default=1.0)

INIT_API_KEYS = [
    {
        "name": "OpenAI",
        "llm_type": "openai",
        "key": OPENAI_API_KEY,
    },
    {
        "name": "Anthropic",
        "llm_type": "anthropic",
        "key": env.str("ANTHROPIC_API_KEY", default=""),
    },
]

GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")

FAKE_LLM_REQUEST = env.bool("FAKE_LLM_REQUEST", default=False)
# FAKE_LLM_REQUEST = False
# FAKE_LLM_REQUEST = True
FAKE_LLM_DELAY = env.int("FAKE_LLM_DELAY", default=0.03)
