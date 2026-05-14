"""
Critical rate-limit tests:
  - requests succeed up to the daily limit
  - the request past the limit returns 429 with a clear payload
  - the counter resets after the UTC midnight window passes
  - limits are tracked per (user, endpoint), not globally
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.chat.models import ChatSession
from apps.ratelimit.models import RateLimit

User = get_user_model()

LOGIN_URL = reverse("auth-login")
SCAN_URL = reverse("analyzer-scan")

CREDENTIALS = {"email": "limited@example.com", "password": "StrongPass123!"}

MOCK_SCAN_RESULT = {
    "vulnerabilities": [],
    "summary": "No issues found.",
    "risk_score": 0,
}
VULNERABLE_CODE = "query = 'SELECT * FROM users WHERE id = ' + user_input"


@override_settings(RATE_LIMITS={"chat_messages": 3, "analyzer_scan": 2})
class ChatRateLimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.session = ChatSession.objects.create(user=self.user)
        self.url = reverse("chat-messages", args=[self.session.pk])

    @patch("apps.chat.views.chat_completion", return_value="ok")
    def test_requests_succeed_up_to_limit(self, _mock):
        for _ in range(3):
            res = self.client.post(self.url, {"content": "hi"}, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rate_limit = RateLimit.objects.get(user=self.user, endpoint="chat_messages")
        self.assertEqual(rate_limit.count, 3)

    @patch("apps.chat.views.chat_completion", return_value="ok")
    def test_request_past_limit_returns_429(self, _mock):
        for _ in range(3):
            self.client.post(self.url, {"content": "hi"}, format="json")
        blocked = self.client.post(self.url, {"content": "hi"}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(blocked.data["detail"], "Daily limit reached. Try again tomorrow.")
        self.assertIn("reset_at", blocked.data)
        # The rendered JSON body serialises reset_at as an ISO 8601 UTC string.
        body = json.loads(blocked.content)
        self.assertIsNotNone(body["reset_at"])
        self.assertTrue(body["reset_at"].endswith("Z"))
        # The counter is not incremented past the limit.
        rate_limit = RateLimit.objects.get(user=self.user, endpoint="chat_messages")
        self.assertEqual(rate_limit.count, 3)

    @patch("apps.chat.views.chat_completion", return_value="ok")
    def test_counter_resets_after_utc_midnight(self, _mock):
        for _ in range(3):
            self.client.post(self.url, {"content": "hi"}, format="json")
        self.assertEqual(
            self.client.post(self.url, {"content": "hi"}, format="json").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

        # Simulate the daily window having already expired (past UTC midnight).
        rate_limit = RateLimit.objects.get(user=self.user, endpoint="chat_messages")
        rate_limit.reset_at = timezone.now() - timedelta(seconds=1)
        rate_limit.save(update_fields=["reset_at"])

        res = self.client.post(self.url, {"content": "hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rate_limit.refresh_from_db()
        self.assertEqual(rate_limit.count, 1)
        self.assertGreater(rate_limit.reset_at, timezone.now())

    @patch("apps.chat.views.chat_completion", return_value="ok")
    def test_limit_is_per_user(self, _mock):
        for _ in range(3):
            self.client.post(self.url, {"content": "hi"}, format="json")

        # A different user starts with their own counter at zero.
        other = User.objects.create_user(email="other@example.com", password="StrongPass123!")
        login = self.client.post(
            LOGIN_URL, {"email": other.email, "password": "StrongPass123!"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        other_session = ChatSession.objects.create(user=other)
        res = self.client.post(
            reverse("chat-messages", args=[other_session.pk]),
            {"content": "hi"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    @patch("apps.analyzer.views.analyze_code", return_value=MOCK_SCAN_RESULT)
    @patch("apps.chat.views.chat_completion", return_value="ok")
    def test_chat_limit_does_not_block_analyzer(self, _chat, _scan):
        # Exhaust the chat daily limit.
        for _ in range(3):
            self.client.post(self.url, {"content": "hi"}, format="json")
        self.assertEqual(
            self.client.post(self.url, {"content": "hi"}, format="json").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        # The analyzer counter is tracked separately — scans still go through.
        res = self.client.post(
            SCAN_URL, {"code": VULNERABLE_CODE, "language": "python"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            RateLimit.objects.get(user=self.user, endpoint="analyzer_scan").count, 1
        )


@override_settings(RATE_LIMITS={"chat_messages": 3, "analyzer_scan": 2})
class AnalyzerRateLimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    @patch("apps.analyzer.views.analyze_code", return_value=MOCK_SCAN_RESULT)
    def test_scan_requests_succeed_up_to_limit(self, _mock):
        for _ in range(2):
            res = self.client.post(
                SCAN_URL, {"code": VULNERABLE_CODE, "language": "python"}, format="json"
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

    @patch("apps.analyzer.views.analyze_code", return_value=MOCK_SCAN_RESULT)
    def test_scan_request_past_limit_returns_429(self, _mock):
        for _ in range(2):
            self.client.post(
                SCAN_URL, {"code": VULNERABLE_CODE, "language": "python"}, format="json"
            )
        blocked = self.client.post(
            SCAN_URL, {"code": VULNERABLE_CODE, "language": "python"}, format="json"
        )
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(blocked.data["detail"], "Daily limit reached. Try again tomorrow.")
        self.assertIn("reset_at", blocked.data)
