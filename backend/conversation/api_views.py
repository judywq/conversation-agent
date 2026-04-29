from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.conversation.services.profile_audio import generate_cefr_topic_samples
from backend.conversation.services.stt import transcribe_audio_file


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


class CefrTopicSamplesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CefrTopicSamplesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topic = serializer.validated_data["topic"]
        samples = generate_cefr_topic_samples(topic=topic)
        if hasattr(request.user, "userprofile"):
            request.user.userprofile.cefr_sample_choices = samples
            request.user.userprofile.save(update_fields=["cefr_sample_choices"])
        return Response({"topic": topic, "samples": samples})

