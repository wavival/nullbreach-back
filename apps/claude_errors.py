import logging
from typing import Optional

import anthropic
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def handle_claude_error(exc: anthropic.APIError) -> Optional[Response]:
    """Map an anthropic.APIError subclass to a DRF Response.

    Logs the full exception server-side and returns a user-safe message.
    Returns None if exc is not a recognised anthropic error (caller should re-raise).
    """
    if isinstance(exc, anthropic.AuthenticationError):
        logger.error("Claude authentication failed: %s", exc, exc_info=True)
        return Response(
            {"detail": "AI service authentication failed. Please contact support."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, anthropic.NotFoundError):
        logger.error("Claude resource not found: %s", exc, exc_info=True)
        return Response(
            {"detail": "AI model or resource not available."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, anthropic.RateLimitError):
        logger.warning("Claude rate limit exceeded: %s", exc)
        response = Response(
            {"detail": "AI service is busy. Please try again in a moment."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        raw_response = getattr(exc, "response", None)
        retry_after = raw_response.headers.get("retry-after") if raw_response else None
        if retry_after:
            response["Retry-After"] = retry_after
        return response

    if isinstance(exc, anthropic.APIError):
        logger.error("Claude API error: %s", exc, exc_info=True)
        return Response(
            {"detail": "AI service is temporarily unavailable. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return None
