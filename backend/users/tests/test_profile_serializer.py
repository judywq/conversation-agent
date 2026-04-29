import pytest

from backend.users.api.serializers import CustomUserDetailsSerializer


@pytest.mark.django_db
def test_profile_completed_updates_when_all_ocean_traits_present(user):
    serializer = CustomUserDetailsSerializer(
        instance=user,
        data={
            "ocean": {
                "openness": "low",
                "conscientiousness": "medium",
                "extraversion": "high",
                "agreeableness": "medium",
                "neuroticism": "low",
            },
        },
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    user.refresh_from_db()
    assert user.userprofile.profile_completed is True
