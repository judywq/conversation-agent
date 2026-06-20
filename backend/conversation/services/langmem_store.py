from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any
from typing import Iterator

from django.conf import settings
from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

_store_lock = threading.Lock()
_postgres_store: BaseStore | None = None
_postgres_store_cm: Any | None = None


def speaker_profiles_enabled() -> bool:
    return bool(getattr(settings, "SPEAKER_PROFILES_ENABLED", True))


def _database_conn_string() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    db = settings.DATABASES["default"]
    engine = db.get("ENGINE", "")
    if "postgresql" not in engine and "postgis" not in engine:
        raise RuntimeError("Speaker profiles require a PostgreSQL DATABASE_URL.")
    user = db.get("USER", "")
    password = db.get("PASSWORD", "")
    host = db.get("HOST", "") or "localhost"
    port = db.get("PORT", "") or "5432"
    name = db.get("NAME", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _build_store_index() -> dict[str, Any] | None:
    provider = str(getattr(settings, "EMBEDDING_PROVIDER", "openai")).strip().casefold()
    if provider == "fake":
        return None
    model = str(getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")).strip()
    dims = int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))
    return {
        "dims": dims,
        "embed": f"openai:{model}",
    }


def setup_langmem_store(*, store: BaseStore | None = None) -> None:
    target = store or get_postgres_store()
    target.setup()


def get_postgres_store() -> BaseStore:
    if not speaker_profiles_enabled():
        raise RuntimeError("Speaker profiles are disabled (SPEAKER_PROFILES_ENABLED=False).")
    global _postgres_store, _postgres_store_cm
    with _store_lock:
        if _postgres_store is not None:
            return _postgres_store
        from langgraph.store.postgres import PostgresStore

        index = _build_store_index()
        kwargs: dict[str, Any] = {}
        if index is not None:
            kwargs["index"] = index
        _postgres_store_cm = PostgresStore.from_conn_string(
            _database_conn_string(),
            **kwargs,
        )
        _postgres_store = _postgres_store_cm.__enter__()
        logger.info("Initialized LangGraph PostgresStore for speaker profiles.")
        return _postgres_store


def reset_postgres_store_cache() -> None:
    global _postgres_store, _postgres_store_cm
    with _store_lock:
        if _postgres_store_cm is not None:
            try:
                _postgres_store_cm.__exit__(None, None, None)
            except Exception:
                logger.exception("Failed to close PostgresStore context manager.")
        _postgres_store = None
        _postgres_store_cm = None


@contextmanager
def speaker_profile_store(store: BaseStore | None = None) -> Iterator[BaseStore]:
    if store is not None:
        yield store
        return
    if not speaker_profiles_enabled():
        raise RuntimeError("Speaker profiles are disabled (SPEAKER_PROFILES_ENABLED=False).")
    yield get_postgres_store()
