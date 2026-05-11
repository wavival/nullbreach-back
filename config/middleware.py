import logging
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("audit")


class RequestAuditMiddleware:
    """Log every request as `METHOD PATH STATUS DURATIONms user=<id>`.

    `user_id` is captured for audit trails (no PII — the integer pk only).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = int((time.monotonic() - start) * 1000)
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and user.is_authenticated else None
        logger.info(
            "%s %s %d %dms user=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            user_id if user_id is not None else "-",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
            },
        )
        return response
