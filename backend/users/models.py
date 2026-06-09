from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Default custom user model for ATG.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    must_change_password = models.BooleanField(default=False)
    is_demo_account = models.BooleanField(
        default=False,
        help_text="Whether this is a demo account that should use demo prompts",
    )

    # Conversation system profile fields
    ocean = models.JSONField(
        default=dict,
        blank=True,
        help_text="OCEAN self-evaluation levels, e.g. {'openness': 'high', ...}.",
    )
    cefr_level = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="CEFR level (e.g., A1, A2, B1, B2, C1, C2).",
    )
    profile_completed = models.BooleanField(
        default=False,
        help_text="Whether the user has completed the required personality profile.",
    )
    cefr_sample_topic = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Topic for which the latest CEFR listening choice was confirmed.",
    )
    cefr_sample_choices = models.JSONField(
        default=list,
        blank=True,
        help_text="Latest generated CEFR listening samples for the selected topic.",
    )

    preferred_name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="How the user would like to be addressed in the conversation.",
    )

    major = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="User's academic major / field of study. Used as the default major for agents in their conversation sessions.",
    )

    discussion_category = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Selected news taxonomy category slug for the pending discussion.",
    )
    discussion_subtopic = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Selected news taxonomy subtopic slug for the pending discussion.",
    )
    discussion_scenario = models.TextField(
        blank=True,
        default="",
        help_text="LLM-generated discussion scenario for the pending conversation.",
    )
    discussion_article_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional news article id used as scenario context.",
    )
    discussion_article_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="News article PKs selected for the pending discussion knowledge base.",
    )

    def __str__(self) -> str:
        return f"{self.user.name} ({self.user.email})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "userprofile"):
        instance.userprofile.save()
