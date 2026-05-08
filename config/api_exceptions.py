from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from backend.conversation.exceptions import ServiceConfigurationError


def custom_exception_handler(exc, context):
    """
    Ensure predictable JSON errors for known runtime misconfiguration cases.
    """
    if isinstance(exc, ServiceConfigurationError):
        return Response(
            {"detail": str(exc), "code": exc.code},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return exception_handler(exc, context)

