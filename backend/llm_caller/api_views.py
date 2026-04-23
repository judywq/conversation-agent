from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LLMModel


class ActiveModelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        models_qs = LLMModel.get_active_models()
        payload = [
            {
                "id": m.id,
                "name": m.name,
                "display_name": m.display_name,
                "llm_type": m.llm_type,
                "is_default": m.is_default,
            }
            for m in models_qs
        ]
        return Response(payload)

