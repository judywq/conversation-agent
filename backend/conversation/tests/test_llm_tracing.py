from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from backend.conversation.services import speaker_profiles as speaker_profiles_service
from backend.conversation.services.llm_tracing import conversation_tracing_context
from backend.conversation.services.llm_tracing import invoke_chat_llm
from backend.conversation.services.llm_tracing import user_tracing_enabled


@pytest.mark.django_db
def test_user_tracing_enabled_for_staff(user) -> None:
    user.is_staff = True
    user.is_superuser = False
    user.save(update_fields=["is_staff", "is_superuser"])
    assert user_tracing_enabled(user) is True


@pytest.mark.django_db
def test_user_tracing_enabled_for_superuser(user) -> None:
    user.is_staff = False
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    assert user_tracing_enabled(user) is True


@pytest.mark.django_db
def test_user_tracing_disabled_for_normal_user(user) -> None:
    user.is_staff = False
    user.is_superuser = False
    user.save(update_fields=["is_staff", "is_superuser"])
    assert user_tracing_enabled(user) is False


def test_user_tracing_disabled_without_user() -> None:
    assert user_tracing_enabled(None) is False


def test_invoke_chat_llm_uses_tracing_context_for_staff_user(user, monkeypatch) -> None:
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    contexts: list[bool] = []
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = "ok"

    class FakeTracingContext:
        def __init__(self, **kwargs):
            contexts.append(kwargs.get("enabled"))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.conversation.services.llm_tracing.ls.tracing_context",
        lambda **kwargs: FakeTracingContext(**kwargs),
    )

    result = invoke_chat_llm(fake_llm, ["message"], user=user)

    assert result == "ok"
    fake_llm.invoke.assert_called_once_with(["message"])
    assert contexts == [True]


def test_invoke_chat_llm_disables_tracing_for_normal_user(user, monkeypatch) -> None:
    user.is_staff = False
    user.is_superuser = False

    contexts: list[bool] = []
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = "ok"

    class FakeTracingContext:
        def __init__(self, **kwargs):
            contexts.append(kwargs.get("enabled"))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.conversation.services.llm_tracing.ls.tracing_context",
        lambda **kwargs: FakeTracingContext(**kwargs),
    )

    invoke_chat_llm(fake_llm, ["message"], user=user)

    assert contexts == [False]


def test_invoke_chat_llm_uses_bound_conversation_user(user, monkeypatch) -> None:
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    contexts: list[bool] = []
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = "ok"

    class FakeTracingContext:
        def __init__(self, **kwargs):
            contexts.append(kwargs.get("enabled"))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.conversation.services.llm_tracing.ls.tracing_context",
        lambda **kwargs: FakeTracingContext(**kwargs),
    )

    with conversation_tracing_context(user):
        invoke_chat_llm(fake_llm, ["message"])

    assert contexts == [True]


def test_extract_and_update_profiles_still_invokes_when_tracing_disabled(user, monkeypatch, settings) -> None:
    settings.FAKE_LLM_REQUEST = False
    settings.LANGMEM_ENABLED = True
    settings.LANGMEM_PROFILE_EXTRACTION_ENABLED = True
    settings.SPEAKER_PROFILES_ENABLED = True

    invoked: list[str] = []

    @contextmanager
    def fake_store_cm(store=None):
        yield MagicMock()

    monkeypatch.setattr(speaker_profiles_service, "langmem_enabled", lambda: True)
    monkeypatch.setattr(speaker_profiles_service, "speaker_profile_store", fake_store_cm)
    monkeypatch.setattr(
        speaker_profiles_service,
        "_user_memory_manager",
        lambda store: MagicMock(),
    )
    monkeypatch.setattr(speaker_profiles_service, "sanitize_namespace_memories", lambda store, ns: None)

    def track_invoke(runnable, payload, *, user=None, config=None):
        invoked.append("user")
        return {"ok": True}

    monkeypatch.setattr(speaker_profiles_service, "invoke_runnable", track_invoke)

    speaker_profiles_service.extract_and_update_profiles(
        user,
        [{"role": "user", "content": "[user] I study biology."}],
    )

    assert invoked == ["user"]
