import pytest

from backend.users.api.serializers import CustomUserDetailsSerializer


@pytest.mark.django_db
def test_profile_completed_requires_ocean_and_cefr(user):
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
    assert user.userprofile.profile_completed is False

    serializer = CustomUserDetailsSerializer(
        instance=user,
        data={"cefr_level": "B1"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    user.refresh_from_db()
    assert user.userprofile.profile_completed is True


@pytest.mark.django_db
def test_major_round_trips_through_serializer(user):
    serializer = CustomUserDetailsSerializer(
        instance=user,
        data={"major": "Computer Science"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    user.refresh_from_db()
    assert user.userprofile.major == "Computer Science"
    assert serializer.data["major"] == "Computer Science"
