from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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

