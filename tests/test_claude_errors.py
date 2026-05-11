"""
Unit tests for apps.claude_errors.handle_claude_error — covers each
anthropic.APIError subclass branch in isolation so the mapping cannot
silently regress when the SDK is upgraded.
"""
from types import SimpleNamespace

import anthropic
from django.test import TestCase
from rest_framework import status

from apps.claude_errors import handle_claude_error


class _FakeResponse:
    def __init__(self, headers=None):
        self.headers = headers or {}


class HandleClaudeErrorTests(TestCase):
    def test_authentication_error_returns_401(self):
        exc = anthropic.AuthenticationError(
            message="bad key",
            response=SimpleNamespace(status_code=401, headers={}, request=None),
            body=None,
        )
        res = handle_claude_error(exc)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", res.data)

    def test_not_found_error_returns_404(self):
        exc = anthropic.NotFoundError(
            message="model gone",
            response=SimpleNamespace(status_code=404, headers={}, request=None),
            body=None,
        )
        res = handle_claude_error(exc)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_rate_limit_error_returns_429_with_retry_after(self):
        exc = anthropic.RateLimitError(
            message="slow down",
            response=SimpleNamespace(
                status_code=429, headers={"retry-after": "7"}, request=None
            ),
            body=None,
        )
        res = handle_claude_error(exc)
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res["Retry-After"], "7")

    def test_rate_limit_error_without_retry_after_header(self):
        exc = anthropic.RateLimitError(
            message="slow down",
            response=SimpleNamespace(status_code=429, headers={}, request=None),
            body=None,
        )
        res = handle_claude_error(exc)
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertNotIn("Retry-After", res)

    def test_api_connection_error_returns_502(self):
        exc = anthropic.APIConnectionError(request=None)
        res = handle_claude_error(exc)
        self.assertEqual(res.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_non_anthropic_exception_returns_none(self):
        self.assertIsNone(handle_claude_error(ValueError("not an APIError")))
