import json
import logging

import anthropic
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.claude_errors import handle_claude_error
from apps.throttles import ClaudeScanThrottle
from .claude import analyze_code
from .serializers import ScanRequestSerializer, ScanResultSerializer

logger = logging.getLogger(__name__)


class ScanView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ClaudeScanThrottle]

    @extend_schema(
        request=ScanRequestSerializer,
        responses={200: ScanResultSerializer},
        summary="Analyze a code snippet for OWASP Top 10 vulnerabilities",
        tags=["analyzer"],
    )
    def post(self, request):
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
            # Return raw result if structure is unexpected
            return Response(result)

        return Response(out.data)
