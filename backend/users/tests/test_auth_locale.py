import json
import re

import pytest
from django.http import HttpResponse
from django.middleware.locale import LocaleMiddleware
from django.test import RequestFactory
from django.utils.translation import get_language
from rest_framework.test import APIClient

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def test_locale_middleware_keeps_english_for_zh_accept_language() -> None:
    factory = RequestFactory()
    request = factory.get("/", HTTP_ACCEPT_LANGUAGE="zh-CN,zh;q=0.9")

    def get_response(_request):
        assert get_language() == "en"
        return HttpResponse("ok")

    LocaleMiddleware(get_response)(request)


@pytest.mark.django_db
def test_password_change_validation_errors_stay_english(user) -> None:
    password = "ValidOldPass1"
    user.set_password(password)
    user.save()

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/dj-rest-auth/password/change/",
        data=json.dumps(
            {
                "old_password": password,
                "new_password1": "123",
                "new_password2": "123",
            },
        ),
        content_type="application/json",
        HTTP_ACCEPT_LANGUAGE="zh-CN,zh;q=0.9",
    )

    assert response.status_code == 400
    body = json.dumps(response.data, ensure_ascii=False)
    assert _CJK_RE.search(body) is None
    assert "password" in body.casefold()
