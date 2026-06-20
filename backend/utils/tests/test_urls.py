from django.test import TestCase, override_settings

from backend.utils.urls import absolute_media_url


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
