import json

import anthropic
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .claude import analyze_code
from .serializers import ScanRequestSerializer, ScanResultSerializer


class ScanView(APIView):
    permission_classes = [IsAuthenticated]

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
            return Response(
                {"detail": f"Claude API error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return Response(
                {"detail": f"Failed to parse analysis result: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        out = ScanResultSerializer(data=result)
        if not out.is_valid():
            # Return raw result if structure is unexpected
            return Response(result)

        return Response(out.data)
