from django.test import TestCase, override_settings

from backend.utils.urls import absolute_media_url
from backend.utils.urls import ensure_absolute_url


@override_settings(DEBUG=False, DOMAIN_NAME="example.test", MEDIA_URL="/media/")
class AbsoluteMediaUrlTests(TestCase):
    def test_uses_https_when_not_debug(self) -> None:
        assert absolute_media_url("audio/test.mp3") == "https://example.test/media/audio/test.mp3"

    @override_settings(DEBUG=True)
    def test_uses_http_when_debug(self) -> None:
        assert absolute_media_url("audio/test.mp3") == "http://example.test/media/audio/test.mp3"

    @override_settings(DOMAIN_NAME="https://cdn.example.test")
    def test_respects_explicit_scheme_in_domain_name(self) -> None:
        assert absolute_media_url("audio/test.mp3") == "https://cdn.example.test/media/audio/test.mp3"


@override_settings(DEBUG=False, DOMAIN_NAME="example.test", MEDIA_URL="/media/")
class EnsureAbsoluteUrlTests(TestCase):
    def test_returns_none_for_empty(self) -> None:
        assert ensure_absolute_url(None) is None
        assert ensure_absolute_url("") is None

    def test_leaves_absolute_urls_unchanged(self) -> None:
        url = "https://cdn.example.test/media/audio/test.mp3"
        assert ensure_absolute_url(url) == url

    def test_prefixes_relative_media_path(self) -> None:
        assert (
            ensure_absolute_url("/media/conversation/user_audio/session_1/user_1/clip.webm")
            == "https://example.test/media/conversation/user_audio/session_1/user_1/clip.webm"
        )

    @override_settings(DEBUG=True, DOMAIN_NAME="localhost:8000")
    def test_prefixes_relative_path_with_http_in_debug(self) -> None:
        assert (
            ensure_absolute_url("/media/foo.webm")
            == "http://localhost:8000/media/foo.webm"
        )

    def test_prefixes_path_without_leading_slash(self) -> None:
        assert ensure_absolute_url("media/foo.webm") == "https://example.test/media/foo.webm"
