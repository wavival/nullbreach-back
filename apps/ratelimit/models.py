from django.conf import settings
from django.db import models


class RateLimit(models.Model):
    """Daily request counter, per user and endpoint.

    Persisted in the DB so it survives process restarts and is shared across
    gunicorn workers (unlike DRF throttling, which lives in the cache). The
    counter resets once `reset_at` has passed — see
    `apps.ratelimit.decorators.check_rate_limit`.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rate_limits",
    )
    endpoint = models.CharField(max_length=64)
    count = models.PositiveIntegerField(default=0)
    reset_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One row per (user, endpoint). The unique index this constraint
            # creates also covers the decorator's canonical lookup, so no extra
            # models.Index over the same fields is needed.
            models.UniqueConstraint(
                fields=["user", "endpoint"],
                name="ratelimit_user_endpoint_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} · {self.endpoint} · {self.count}"
