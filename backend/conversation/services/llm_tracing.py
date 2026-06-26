from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import langsmith as ls

_conversation_user: ContextVar[Any | None] = ContextVar("conversation_user", default=None)


def user_tracing_enabled(user: Any | None) -> bool:
    if user is None:
        return False
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _langsmith_project_name() -> str | None:
    return os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT") or None


def resolve_tracing_user(explicit_user: Any | None = None) -> Any | None:
    if explicit_user is not None:
        return explicit_user
    return _conversation_user.get()


@contextmanager
def conversation_tracing_context(user: Any | None):
    """Bind the session user for nested LLM calls (e.g. background threads, WebSocket handlers)."""
    token = _conversation_user.set(user)
    try:
        yield
    finally:
        _conversation_user.reset(token)


def _tracing_context_kwargs(user: Any | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"enabled": user_tracing_enabled(user)}
    project_name = _langsmith_project_name()
    if project_name:
        kwargs["project_name"] = project_name
    return kwargs


def invoke_chat_llm(
    llm: Any,
    messages: Any,
    *,
    user: Any | None = None,
    config: Any | None = None,
) -> Any:
    effective_user = resolve_tracing_user(user)
    with ls.tracing_context(**_tracing_context_kwargs(effective_user)):
        if config is not None:
            return llm.invoke(messages, config=config)
        return llm.invoke(messages)


def invoke_runnable(
    runnable: Any,
    input: Any,
    *,
    user: Any | None = None,
    config: Any | None = None,
) -> Any:
    effective_user = resolve_tracing_user(user)
    with ls.tracing_context(**_tracing_context_kwargs(effective_user)):
        if config is not None:
            return runnable.invoke(input, config=config)
        return runnable.invoke(input)
