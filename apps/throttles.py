from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class _LiveRateMixin:
    """Re-read the rate from `api_settings` on every instantiation.

    DRF's SimpleRateThrottle caches `THROTTLE_RATES` as a class attribute at
    import time, so `@override_settings` in tests does not propagate. Re-reading
    in `get_rate` keeps the throttle in sync with the current settings.
    """

    def get_rate(self) -> str:
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]


class ClaudeChatThrottle(_LiveRateMixin, UserRateThrottle):
    scope = "claude_chat"


class ClaudeScanThrottle(_LiveRateMixin, UserRateThrottle):
    scope = "claude_scan"


class AuthAnonThrottle(_LiveRateMixin, AnonRateThrottle):
    """Per-IP throttle for unauthenticated auth endpoints (login, register).

    Mitigates credential-stuffing and registration enumeration; rate lives in
    the `auth` scope (see DEFAULT_THROTTLE_RATES).
    """

    scope = "auth"
