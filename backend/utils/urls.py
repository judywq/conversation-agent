from django.conf import settings


def _absolute_base() -> str:
    domain = settings.DOMAIN_NAME.strip()
    if domain.startswith(("http://", "https://")):
        return domain.rstrip("/")
    scheme = "http" if settings.DEBUG else "https"
    return f"{scheme}://{domain.rstrip('/')}"


def absolute_media_url(stored_path: str) -> str:
    """Build an absolute URL for a path returned by default_storage.save()."""
    media_url = settings.MEDIA_URL
    if not media_url.endswith("/"):
        media_url = f"{media_url}/"

    return f"{_absolute_base()}{media_url}{stored_path.lstrip('/')}"


def ensure_absolute_url(url: str | None) -> str | None:
    """Leave absolute URLs unchanged; prefix relative paths with DOMAIN_NAME base."""
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"{_absolute_base()}{url}"
    return f"{_absolute_base()}/{url}"
