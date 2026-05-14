import functools
import logging
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response

from .models import RateLimit

logger = logging.getLogger(__name__)


def _next_utc_midnight(now=None):
    """Return the next UTC midnight (timezone-aware).

    Marks the instant the counter's daily window expires.
    """
    now = now or timezone.now()
    tomorrow = (now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, time.min, tzinfo=dt_timezone.utc)


def check_rate_limit(endpoint, limit_key):
    """Apply a daily per-user limit to an APIView method.

    `endpoint` identifies the row in the RateLimit table; `limit_key` indexes
    `settings.RATE_LIMITS`. Behaviour:
      - If `reset_at` has passed, reset the counter to 0 and reschedule the window.
      - If `count >= limit`, respond 429 without running the view.
      - Otherwise, increment the counter and let the request through.

    Every check is logged to the `apps` logger for debugging.
    """

    def decorator(view_method):
        @functools.wraps(view_method)
        def _wrapped(self, request, *args, **kwargs):
            limit = settings.RATE_LIMITS[limit_key]
            user = request.user

            with transaction.atomic():
                # select_for_update locks the row for the transaction to avoid
                # races between workers incrementing the same counter.
                rate_limit, _created = RateLimit.objects.select_for_update().get_or_create(
                    user=user,
                    endpoint=endpoint,
                    defaults={"reset_at": _next_utc_midnight()},
                )

                now = timezone.now()
                # Daily window expired: reset the counter and reschedule.
                if rate_limit.reset_at <= now:
                    rate_limit.count = 0
                    rate_limit.reset_at = _next_utc_midnight(now)

                if rate_limit.count >= limit:
                    logger.warning(
                        "rate limit BLOCKED user=%s endpoint=%s count=%s limit=%s reset_at=%s",
                        user.pk,
                        endpoint,
                        rate_limit.count,
                        limit,
                        rate_limit.reset_at.isoformat(),
                    )
                    return Response(
                        {
                            "detail": "Daily limit reached. Try again tomorrow.",
                            "reset_at": rate_limit.reset_at,
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                rate_limit.count += 1
                rate_limit.save(update_fields=["count", "reset_at", "updated_at"])
                logger.info(
                    "rate limit OK user=%s endpoint=%s count=%s limit=%s reset_at=%s",
                    user.pk,
                    endpoint,
                    rate_limit.count,
                    limit,
                    rate_limit.reset_at.isoformat(),
                )

            return view_method(self, request, *args, **kwargs)

        return _wrapped

    return decorator
