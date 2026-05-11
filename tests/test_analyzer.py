"""
Critical analyzer tests:
  - authenticated scan returns structured vulnerabilities
  - unauthenticated scan returns 401
  - empty code is rejected
  - Claude API error surfaces as 502
  - malformed Claude payload surfaces as 502
"""
import json
from unittest.mock import patch

import anthropic
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

LOGIN_URL = reverse("auth-login")
SCAN_URL = reverse("analyzer-scan")

CREDENTIALS = {"email": "scanner@example.com", "password": "StrongPass123!"}

MOCK_RESULT = {
    "vulnerabilities": [
        {
            "id": "A03:2021",
            "name": "Injection",
            "severity": "critical",
            "line": 1,
            "description": "Raw SQL concatenation.",
            "recommendation": "Use parameterized queries.",
        }
    ],
    "summary": "Critical SQL injection found.",
    "risk_score": 90,
}

VULNERABLE_CODE = "query = 'SELECT * FROM users WHERE id = ' + user_input"


class ScanTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    @patch("apps.analyzer.views.analyze_code", return_value=MOCK_RESULT)
    def test_scan_returns_structured_result(self, mock_analyze):
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE, "language": "python"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("vulnerabilities", res.data)
        self.assertIn("risk_score", res.data)
        self.assertIn("summary", res.data)
        self.assertEqual(res.data["vulnerabilities"][0]["severity"], "critical")
        mock_analyze.assert_called_once_with(VULNERABLE_CODE, "python")

    @patch("apps.analyzer.views.analyze_code", return_value=MOCK_RESULT)
    def test_scan_without_language_uses_default(self, mock_analyze):
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mock_analyze.assert_called_once_with(VULNERABLE_CODE, "")

    def test_scan_unauthenticated_returns_401(self):
        self.client.credentials()
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_scan_empty_code_returns_400(self):
        res = self.client.post(SCAN_URL, {"code": ""}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_scan_missing_code_returns_400(self):
        res = self.client.post(SCAN_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.analyzer.views.analyze_code", side_effect=anthropic.APIConnectionError(request=None))
    def test_scan_claude_api_error_returns_502(self, _mock):
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE}, format="json")
        self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("detail", res.data)

    @patch(
        "apps.analyzer.views.analyze_code",
        side_effect=json.JSONDecodeError("Expecting value", "garbage", 0),
    )
    def test_scan_malformed_json_returns_502(self, _mock):
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE}, format="json")
        self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("detail", res.data)

    @patch(
        "apps.analyzer.views.analyze_code",
        return_value={"unexpected": "shape", "no_vulnerabilities_key": True},
    )
    def test_scan_unexpected_shape_returns_502(self, _mock):
        res = self.client.post(SCAN_URL, {"code": VULNERABLE_CODE}, format="json")
        self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("detail", res.data)
