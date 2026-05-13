import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from backend.llm_caller.models import LLMModel
from backend.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def active_model():
    return LLMModel.objects.create(
        name="gpt-4",
        display_name="GPT-4",
        is_active=True,
        is_default=True,
    )


class TestActiveModelsView:
    def test_unauthenticated_access(self, api_client):
        url = reverse("llm-active-models")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_active_models(self, authenticated_client, active_model):
        url = reverse("llm-active-models")

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == [
            {
                "id": active_model.id,
                "name": active_model.name,
                "display_name": active_model.display_name,
                "llm_type": active_model.llm_type,
                "is_default": active_model.is_default,
            },
        ]
