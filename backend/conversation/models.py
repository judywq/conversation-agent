from django.conf import settings
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from pgvector.django import HnswIndex
from pgvector.django import VectorField

from backend.core.models import TimestampedBase


def user_audio_upload_to(instance: "UserAudio", filename: str) -> str:
    # Keep media paths deterministic and grouped by session/user.
    session_id = instance.session_id or "unknown_session"
    user_id = instance.user_id or "unknown_user"
    return f"conversation/user_audio/session_{session_id}/user_{user_id}/{filename}"


class ConversationSession(TimestampedBase):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_sessions",
    )
    topic = models.CharField(max_length=500, blank=True, default="")
    news_category = models.CharField(max_length=100, blank=True, default="")
    news_subtopic = models.CharField(max_length=100, blank=True, default="")
    scenario = models.TextField(blank=True, default="")
    news_article = models.ForeignKey(
        "news.NewsArticle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversation_sessions",
    )
    discussion_article_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="News article PKs selected as session knowledge base for RAG.",
    )

    # ConversationState (spec-aligned)
    turn_count = models.IntegerField(default=0)
    previous_speaker = models.CharField(max_length=100, null=True, blank=True)
    pending_forced_user_turn = models.BooleanField(default=False)
    # User override flag (e.g., "raise hand" request to speak)
    user_override_requested = models.BooleanField(default=False)
    terminate = models.BooleanField(default=False)
    paused = models.BooleanField(default=False)

    max_turns = models.IntegerField(default=20)
    agent_count = models.IntegerField(default=3)

    # Running counts of speech acts for facilitator target-mix guidance (major + ASSERTIVES/DIRECTIVES subtypes).
    speech_act_counters = models.JSONField(default=dict, blank=True)

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
    display_name = models.CharField(max_length=80, blank=True, default="")
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
    utterance_tts = models.TextField(
        blank=True,
        default="",
        help_text="Agent-only: text sent to the TTS provider, with audio tags preserved. Empty for user turns.",
    )

    # Facilitator metadata (or generated for user)
    speech_act = models.CharField(max_length=50, blank=True, default="")
    subtype = models.CharField(max_length=50, null=True, blank=True)
    target = models.CharField(max_length=200, null=True, blank=True)

    turn_index = models.IntegerField()
    subturn_index = models.IntegerField(default=0)

    # Web / audio metadata
    source = models.CharField(max_length=50, null=True, blank=True)  # e.g., "mic", "text"
    audio_url = models.URLField(max_length=1000, null=True, blank=True)

    # Agent utterance duplicate detection (vs prior agent turns in the same session).
    duplicate_similarity_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    duplicate_is_repetition = models.BooleanField(null=True, blank=True)
    duplicate_threshold = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    duplicate_matched_turn = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicate_matches",
    )
    duplicate_matched_utterance = models.TextField(blank=True, default="")
    duplicate_matched_speaker = models.CharField(max_length=100, blank=True, default="")
    duplicate_matched_turn_index = models.IntegerField(null=True, blank=True)
    duplicate_matched_subturn_index = models.IntegerField(null=True, blank=True)
    duplicate_reason = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["turn_index", "subturn_index"]
        unique_together = [("session", "turn_index", "subturn_index")]

    def __str__(self) -> str:
        return f"TurnRecord({self.session_id}#{self.turn_index}.{self.subturn_index}, {self.speaker_type}:{self.speaker})"


class UserAudio(TimestampedBase):
    """
    Stored user-recorded audio (the user's real voice).
    Uploaded by the web client and linked to a session and (optionally) a specific turn.
    """

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name="user_audios",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_user_audios",
    )
    turn = models.ForeignKey(
        TurnRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_audios",
    )
    audio_file = models.FileField(upload_to=user_audio_upload_to)
    content_type = models.CharField(max_length=100, blank=True, default="")
    original_filename = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="conv_ua_session_ts"),
            models.Index(fields=["user", "-created_at"], name="conv_ua_user_ts"),
        ]

    def __str__(self) -> str:
        return f"UserAudio(session={self.session_id}, user={self.user_id}, file={self.original_filename or self.audio_file.name})"


class TurnEngineLog(TimestampedBase):
    COMPONENT_TURN_MANAGER = "turn_manager"
    COMPONENT_TURN_PROCESSOR = "turn_processor"
    COMPONENT_CHOICES = [
        (COMPONENT_TURN_MANAGER, "Turn manager"),
        (COMPONENT_TURN_PROCESSOR, "Turn processor"),
    ]

    LEVEL_DEBUG = "DEBUG"
    LEVEL_INFO = "INFO"
    LEVEL_WARNING = "WARNING"
    LEVEL_ERROR = "ERROR"
    LEVEL_CHOICES = [
        (LEVEL_DEBUG, "DEBUG"),
        (LEVEL_INFO, "INFO"),
        (LEVEL_WARNING, "WARNING"),
        (LEVEL_ERROR, "ERROR"),
    ]

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name="turn_engine_logs",
    )

    component = models.CharField(max_length=40, choices=COMPONENT_CHOICES)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LEVEL_INFO)

    event = models.CharField(max_length=120, blank=True, default="")
    message = models.TextField(blank=True, default="")
    context = models.JSONField(default=dict, blank=True)

    correlation_id = models.CharField(max_length=64, blank=True, default="")

    turn_index = models.IntegerField(null=True, blank=True)
    subturn_index = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="conv_telog_session_ts"),
            models.Index(fields=["session", "component", "-created_at"], name="conv_telog_comp_ts"),
            models.Index(fields=["session", "level", "-created_at"], name="conv_telog_level_ts"),
        ]

    def __str__(self) -> str:
        return f"TurnEngineLog(session={self.session_id}, {self.component}/{self.level}, event={self.event})"


class SessionNewsChunk(TimestampedBase):
    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name="news_chunks",
    )
    news_article = models.ForeignKey(
        "news.NewsArticle",
        on_delete=models.CASCADE,
        related_name="session_chunks",
    )
    chunk_index = models.PositiveIntegerField(default=0)
    content = models.TextField()
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=100, null=True, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(null=True, blank=True)
    embedding_text_hash = models.CharField(max_length=64, null=True, blank=True, default="")
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("news_article_id", "chunk_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "news_article", "chunk_index"),
                name="unique_session_news_chunk",
            ),
        ]
        indexes = [
            HnswIndex(
                name="conv_news_chunk_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            models.Index(
                fields=("session", "news_article"),
                name="conv_news_chunk_sess_art",
            ),
        ]

    def __str__(self) -> str:
        return f"SessionNewsChunk(session={self.session_id}, article={self.news_article_id}, idx={self.chunk_index})"


class KnowledgeSnippet(TimestampedBase):
    title = models.CharField(max_length=255)
    content = models.TextField()
    source_uri = models.CharField(max_length=1000, blank=True, default="")
    source_label = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=100, null=True, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(null=True, blank=True)
    embedding_text_hash = models.CharField(max_length=64, null=True, blank=True, default="")
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="conv_know_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        ordering = ["title", "id"]

    def __str__(self) -> str:
        return self.title


class UserMemory(TimestampedBase):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="long_term_memories",
    )
    content = models.TextField()
    memory_type = models.CharField(max_length=100, blank=True, default="profile")
    source_uri = models.CharField(max_length=1000, blank=True, default="")
    source_label = models.CharField(max_length=255, blank=True, default="")
    confidence = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=100, null=True, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(null=True, blank=True)
    embedding_text_hash = models.CharField(max_length=64, null=True, blank=True, default="")
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "is_active", "memory_type"],
                name="conv_um_user_active_type_idx",
            ),
            HnswIndex(
                name="conv_user_mem_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        ordering = ["user_id", "memory_type", "id"]

    def __str__(self) -> str:
        return f"UserMemory({self.user_id}, {self.memory_type}, {self.id})"


class TurnRetrieval(TimestampedBase):
    turn = models.ForeignKey(
        TurnRecord,
        on_delete=models.CASCADE,
        related_name="retrieval_traces",
    )
    query = models.TextField(blank=True, default="")
    requested_sources = models.JSONField(default=list, blank=True)
    source_statuses = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list, blank=True)
    rendered_context = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["turn_id", "id"]

    def __str__(self) -> str:
        return f"TurnRetrieval(turn={self.turn_id}, query={self.query})"


class ConversationLLMPrompt(TimestampedBase):
    """
    Legacy prompt storage model kept for backward compatibility.
    Runtime prompt loading now comes from backend/conversation/data/prompts/.
    """

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable id, e.g. agent_utterance or facilitator_plan",
    )
    system_template = models.TextField(help_text="str.format template for the system message")
    user_template = models.TextField(
        blank=True,
        help_text="str.format template for the user/human message. If empty, facilitator uses a JSON body at runtime.",
    )

    class Meta:
        ordering = ["key"]
        verbose_name = "Conversation LLM prompt"
        verbose_name_plural = "Conversation LLM prompts"

    def __str__(self) -> str:
        return f"ConversationLLMPrompt({self.key})"
