import logging
import time

logger = logging.getLogger("audit")


class RequestAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "%s %s %d %dms",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        return response
