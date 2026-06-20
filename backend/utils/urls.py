from django.conf import settings


def absolute_media_url(stored_path: str) -> str:
    """Build an absolute URL for a path returned by default_storage.save()."""
    domain = settings.DOMAIN_NAME.strip()
    if domain.startswith(("http://", "https://")):
        base = domain.rstrip("/")
    else:
        scheme = "http" if settings.DEBUG else "https"
        base = f"{scheme}://{domain.rstrip('/')}"

    media_url = settings.MEDIA_URL
    if not media_url.endswith("/"):
        media_url = f"{media_url}/"

    return f"{base}{media_url}{stored_path.lstrip('/')}"
