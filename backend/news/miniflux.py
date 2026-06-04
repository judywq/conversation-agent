from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


class MinifluxConfigError(RuntimeError):
    pass


class MinifluxRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class MinifluxSettings:
    base_url: str
    api_token: str
    username: str
    password: str
    timeout: float


def get_miniflux_settings() -> MinifluxSettings:
    return MinifluxSettings(
        base_url=settings.MINIFLUX_BASE_URL,
        api_token=settings.MINIFLUX_API_TOKEN,
        username=settings.MINIFLUX_USERNAME,
        password=settings.MINIFLUX_PASSWORD,
        timeout=settings.MINIFLUX_TIMEOUT_SEC,
    )


class MinifluxClient:
    def __init__(  # noqa: PLR0913
        self,
        *,
        base_url: str,
        api_token: str = "",
        username: str = "",
        password: str = "",
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not base_url:
            msg = "MINIFLUX_BASE_URL is required"
            raise MinifluxConfigError(msg)
        if not api_token and not (username and password):
            msg = "Miniflux API token or username/password is required"
            raise MinifluxConfigError(msg)

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        if api_token:
            self.session.headers["X-Auth-Token"] = api_token
        else:
            self.session.auth = (username, password)

    @classmethod
    def from_settings(cls) -> MinifluxClient:
        config = get_miniflux_settings()
        return cls(
            base_url=config.base_url,
            api_token=config.api_token,
            username=config.username,
            password=config.password,
            timeout=config.timeout,
        )

    def list_categories(self) -> list[dict[str, Any]]:
        payload = self._get("/v1/categories")
        if not isinstance(payload, list):
            msg = "Unexpected Miniflux categories response"
            raise MinifluxRequestError(msg)
        return payload

    def fetch_recent_entries(self, *, limit: int) -> dict[str, Any]:
        return self._get(
            "/v1/entries",
            params={
                "direction": "desc",
                "limit": limit,
                "order": "published_at",
            },
        )

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            msg = f"Miniflux request failed: {url}"
            raise MinifluxRequestError(msg) from exc
