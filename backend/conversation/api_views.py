import logging
import time

from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.conversation.models import ConversationSession
from backend.conversation.models import UserAudio
from backend.conversation.services.argument_summary import get_argument_summary_for_session
from backend.conversation.services.session_serialization import session_detail_to_dict
from backend.conversation.services.session_serialization import session_summary_to_dict
from backend.conversation.services.discussion_scenario import DISCUSSION_PROFILE_FIELDS
from backend.conversation.services.discussion_scenario import apply_discussion_result_to_profile
from backend.conversation.services.discussion_scenario import scenario_result_to_dict
from backend.conversation.services.discussion_scenario import setup_discussion_context
from backend.conversation.services.profile_audio import generate_cefr_topic_samples
from backend.conversation.services.stt import transcribe_audio_file
from backend.news.taxonomy import get_category
from backend.news.taxonomy import get_subtopic

logger = logging.getLogger(__name__)


class SpeechToTextView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        audio = request.FILES.get("audio")
        if audio is None:
            return Response({"error": "Missing audio file field 'audio'."}, status=400)

        text = transcribe_audio_file(audio)
        return Response({"text": text})


class CefrTopicSamplesRequestSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=500)


class DiscussionScenarioRequestSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=100)
    subtopic = serializers.CharField(max_length=100)


class DiscussionScenarioView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DiscussionScenarioRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.validated_data["category"]
        subtopic = serializer.validated_data["subtopic"]
        try:
            get_category(category)
            get_subtopic(category, subtopic)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        cefr_level = None
        reference_utterance = None
        if hasattr(request.user, "userprofile"):
            cefr_level = request.user.userprofile.cefr_level
            reference_utterance = request.user.userprofile.proficiency_reference_utterance
        result = setup_discussion_context(
            category=category,
            subtopic=subtopic,
            cefr_level=cefr_level,
            reference_utterance=reference_utterance,
        )
        if hasattr(request.user, "userprofile"):
            profile = request.user.userprofile
            apply_discussion_result_to_profile(profile, result)
            profile.save(update_fields=list(DISCUSSION_PROFILE_FIELDS))
        return Response(scenario_result_to_dict(result))


class CefrTopicSamplesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        t0 = time.perf_counter()
        serializer = CefrTopicSamplesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topic = serializer.validated_data["topic"]
        user_id = request.user.id
        topic_log = topic[:200]
        logger.info("cefr_samples request_start user_id=%s topic=%s", user_id, topic_log)
        try:
            samples = generate_cefr_topic_samples(topic=topic)
            if hasattr(request.user, "userprofile"):
                logger.info("cefr_samples profile_save_start user_id=%s", user_id)
                t_save0 = time.perf_counter()
                request.user.userprofile.cefr_sample_choices = samples
                request.user.userprofile.save(update_fields=["cefr_sample_choices"])
                save_ms = int((time.perf_counter() - t_save0) * 1000)
                logger.info(
                    "cefr_samples profile_save_complete user_id=%s duration_ms=%d",
                    user_id,
                    save_ms,
                )
            else:
                logger.info("cefr_samples profile_save_skipped user_id=%s", user_id)
            total_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "cefr_samples request_complete user_id=%s topic=%s total_ms=%d sample_count=%d",
                user_id,
                topic_log,
                total_ms,
                len(samples),
            )
            return Response({"topic": topic, "samples": samples})
        except Exception:
            total_ms = int((time.perf_counter() - t0) * 1000)
            logger.exception(
                "cefr_samples request_failed user_id=%s topic=%s total_ms=%d",
                user_id,
                topic_log,
                total_ms,
            )
            raise


class UserAudioUploadView(APIView):
    """
    Upload a user-recorded audio clip and return its URL.

    The client should upload the raw recording (e.g. webm) as multipart form field "audio".
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        audio = request.FILES.get("audio")
        if audio is None:
            return Response({"error": "Missing audio file field 'audio'."}, status=400)

        session_id = request.data.get("session_id")
        if not session_id:
            return Response({"error": "Missing required field 'session_id'."}, status=400)

        session = ConversationSession.objects.filter(id=session_id, user=request.user).first()
        if session is None:
            return Response({"error": "Session not found."}, status=404)

        clip = UserAudio.objects.create(
            session=session,
            user=request.user,
            audio_file=audio,
            content_type=str(getattr(audio, "content_type", "") or ""),
            original_filename=str(getattr(audio, "name", "") or ""),
        )

        return Response(
            {
                "id": clip.id,
                "audio_url": clip.audio_file.url,
            },
        )


class SessionArgumentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id: int):
        session = ConversationSession.objects.filter(id=session_id, user=request.user).first()
        if session is None:
            return Response({"detail": "Session not found."}, status=404)
        return Response(get_argument_summary_for_session(session))


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get("limit", 20)), 1), 100)
        except (TypeError, ValueError):
            limit = 20
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        queryset = (
            ConversationSession.objects.filter(user=request.user, turn_count__gt=0)
            .order_by("-created_at")
        )
        total = queryset.count()
        sessions = list(queryset[offset : offset + limit])
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": [session_summary_to_dict(session) for session in sessions],
            },
        )


class SessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id: int):
        session = (
            ConversationSession.objects.filter(id=session_id, user=request.user)
            .prefetch_related("turns")
            .select_related("user__userprofile")
            .first()
        )
        if session is None:
            return Response({"detail": "Session not found."}, status=404)
        return Response(session_detail_to_dict(session))

