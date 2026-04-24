from dj_rest_auth.models import TokenModel
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import LoginSerializer
from dj_rest_auth.serializers import PasswordChangeSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from rest_framework import serializers

from backend.users.models import UserProfile

UserModel = get_user_model()


class UserProfileTextField(serializers.CharField):
    """Reads/writes a `UserProfile` string field while serializer instance is a User."""

    def __init__(self, *, profile_attr: str, **kwargs):
        super().__init__(**kwargs)
        self.profile_attr = profile_attr

    def get_attribute(self, instance):
        profile = getattr(instance, "userprofile", None)
        if not profile:
            return None
        return getattr(profile, self.profile_attr, None)


class UserProfileJSONField(serializers.JSONField):
    """Reads/writes a `UserProfile` JSON field while serializer instance is a User."""

    def __init__(self, *, profile_attr: str, **kwargs):
        super().__init__(**kwargs)
        self.profile_attr = profile_attr

    def get_attribute(self, instance):
        profile = getattr(instance, "userprofile", None)
        if not profile:
            return None
        return getattr(profile, self.profile_attr, None)


class CustomLoginSerializer(LoginSerializer):
    @staticmethod
    def validate_email_verification_status(user, email=None):
        # Skip validation for superusers
        if user.is_superuser:
            return

        # Call parent's static method
        LoginSerializer.validate_email_verification_status(user, email)


class CustomUserDetailsSerializer(UserDetailsSerializer):
    """
    User model w/o password
    """

    must_change_password = serializers.SerializerMethodField()
    ocean = UserProfileJSONField(profile_attr="ocean", required=False)
    cefr_level = UserProfileTextField(
        profile_attr="cefr_level",
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    class Meta:
        extra_fields = []
        # see https://github.com/iMerica/dj-rest-auth/issues/181
        # UserModel.XYZ causing attribute error while importing other
        # classes from `serializers.py`. So, we need to check whether the auth model has
        # the attribute or not
        if hasattr(UserModel, "USERNAME_FIELD"):
            extra_fields.append(UserModel.USERNAME_FIELD)
        if hasattr(UserModel, "EMAIL_FIELD"):
            extra_fields.append(UserModel.EMAIL_FIELD)
        if hasattr(UserModel, "first_name"):
            extra_fields.append("first_name")
        if hasattr(UserModel, "last_name"):
            extra_fields.append("last_name")
        model = UserModel
        fields = (
            "pk",
            *extra_fields,
            "must_change_password",
            "ocean",
            "cefr_level",
        )
        read_only_fields = ("email",)

    def get_must_change_password(self, obj):
        # Return False if no profile exists (shouldn't happen)
        if hasattr(obj, "userprofile"):
            return obj.userprofile.must_change_password
        return False

    def update(self, instance, validated_data):
        ocean = validated_data.pop("ocean", serializers.empty)
        cefr_level = validated_data.pop("cefr_level", serializers.empty)
        user = super().update(instance, validated_data)
        if hasattr(user, "userprofile"):
            update_fields = []
            if ocean is not serializers.empty:
                user.userprofile.ocean = ocean or {}
                update_fields.append("ocean")
            if cefr_level is not serializers.empty:
                user.userprofile.cefr_level = cefr_level or ""
                update_fields.append("cefr_level")
            if update_fields:
                user.userprofile.save(update_fields=update_fields)
        return user


class TokenSerializer(serializers.ModelSerializer):
    user = CustomUserDetailsSerializer()

    class Meta:
        model = TokenModel
        fields = ["key", "created", "user"]


class CustomRegisterSerializer(RegisterSerializer):
    name = serializers.CharField(required=True)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data["name"] = self.validated_data.get("name", "")
        return data

    def save(self, request):
        user = super().save(request)
        user.name = self.cleaned_data.get("name")
        user.save()
        return user


class CustomPasswordChangeSerializer(PasswordChangeSerializer):
    def save(self):
        if hasattr(self.user, "userprofile"):
            self.user.userprofile.must_change_password = False
            self.user.userprofile.save()
        return super().save()
