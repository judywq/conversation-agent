from django.conf import settings
from django.db import models

from backend.core.models import TimestampedBase


class ConversationSession(TimestampedBase):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_sessions",
    )
    topic = models.CharField(max_length=500, blank=True, default="")

    # ConversationState (spec-aligned)
    turn_count = models.IntegerField(default=0)
    previous_speaker = models.CharField(max_length=100, null=True, blank=True)
    pending_forced_user_turn = models.BooleanField(default=False)
    # User override flag (e.g., "raise hand" request to speak)
    user_override_requested = models.BooleanField(default=False)
    terminate = models.BooleanField(default=False)
    paused = models.BooleanField(default=False)

    max_turns = models.IntegerField(default=12)

    def __str__(self) -> str:
        return f"ConversationSession({self.id}, user={self.user_id}, turns={self.turn_count})"


class AgentProfile(TimestampedBase):
    """
    DB-backed agent profile for traceability.
    """

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name="agent_profiles",
    )
    agent_id = models.CharField(max_length=100)
    personality = models.JSONField(default=dict, blank=True)
    traits = models.JSONField(default=dict, blank=True)
    voice = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        unique_together = [("session", "agent_id")]

    def __str__(self) -> str:
        return f"AgentProfile({self.agent_id}, session={self.session_id})"


class TurnRecord(TimestampedBase):
    SPEAKER_TYPE_USER = "user"
    SPEAKER_TYPE_AGENT = "agent"
    SPEAKER_TYPE_MAKESHIFT = "makeshift"
    SPEAKER_TYPE_CHOICES = [
        (SPEAKER_TYPE_USER, "User"),
        (SPEAKER_TYPE_AGENT, "Agent"),
        (SPEAKER_TYPE_MAKESHIFT, "Makeshift"),
    ]

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name="turns",
    )

    speaker = models.CharField(max_length=100)
    speaker_type = models.CharField(
        max_length=20,
        choices=SPEAKER_TYPE_CHOICES,
    )

    utterance = models.TextField()

    # Facilitator metadata (or generated for user)
    speech_act = models.CharField(max_length=50, blank=True, default="")
    subtype = models.CharField(max_length=50, null=True, blank=True)
    target = models.CharField(max_length=200, null=True, blank=True)

    turn_index = models.IntegerField()

    # Web / audio metadata
    source = models.CharField(max_length=50, null=True, blank=True)  # e.g., "mic", "text"
    audio_url = models.URLField(max_length=1000, null=True, blank=True)

    class Meta:
        ordering = ["turn_index"]
        unique_together = [("session", "turn_index")]

    def __str__(self) -> str:
        return f"TurnRecord({self.session_id}#{self.turn_index}, {self.speaker_type}:{self.speaker})"

