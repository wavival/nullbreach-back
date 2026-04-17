from rest_framework.throttling import UserRateThrottle


class ClaudeChatThrottle(UserRateThrottle):
    scope = "claude_chat"


class ClaudeScanThrottle(UserRateThrottle):
    scope = "claude_scan"
