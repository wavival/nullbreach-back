import json
import logging

import anthropic
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.claude_errors import handle_claude_error
from apps.throttles import ClaudeScanThrottle
from .claude import analyze_code
from .serializers import ScanRequestSerializer, ScanResultSerializer

logger = logging.getLogger(__name__)


class ScanView(APIView):
    """Stateless OWASP Top 10 vulnerability scanner.

    Forwards a code snippet to Claude with a JSON-only system prompt, strips
    accidental markdown fences, and re-validates the result through
    `ScanResultSerializer`. Any non-conforming output is surfaced as 502 to
    avoid leaking raw model responses to the client.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ClaudeScanThrottle]

    @extend_schema(
        request=ScanRequestSerializer,
        responses={200: ScanResultSerializer},
        summary="Analyze a code snippet for OWASP Top 10 vulnerabilities",
        tags=["analyzer"],
    )
    def post(self, request: Request) -> Response:
        serializer = ScanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data["code"]
        language = serializer.validated_data["language"]

        try:
            result = analyze_code(code, language)
        except anthropic.APIError as exc:
            return handle_claude_error(exc)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse Claude analysis result: %s", exc, exc_info=True)
            return Response(
                {"detail": "AI service returned an unexpected response. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        out = ScanResultSerializer(data=result)
        if not out.is_valid():
            # Claude returned a shape we cannot validate — surface as 502 rather
            # than leaking the raw payload, which could contain unexpected fields.
            logger.warning("Claude scan result failed schema validation: %s", out.errors)
            return Response(
                {"detail": "AI service returned an unexpected response. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(out.data)
