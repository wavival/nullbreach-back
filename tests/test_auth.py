"""
Critical auth tests:
  - register creates user and returns tokens
  - duplicate email is rejected
  - login returns tokens
  - wrong password is rejected
  - /me requires a valid token
  - logout blacklists the refresh token
  - refresh rotation issues new refresh and blacklists the old one
  - anon throttle blocks brute force on login
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = reverse("auth-register")
LOGIN_URL = reverse("auth-login")
REFRESH_URL = reverse("auth-refresh")
LOGOUT_URL = reverse("auth-logout")
ME_URL = reverse("auth-me")

CREDENTIALS = {"email": "test@example.com", "password": "StrongPass123!"}


class RegisterTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_register_success_returns_generic_202(self):
        res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)
        # No tokens, no user payload — the response shape must be identical
        # to the duplicate-email path so attackers cannot enumerate accounts.
        self.assertNotIn("access", res.data)
        self.assertNotIn("refresh", res.data)
        self.assertNotIn("user", res.data)
        self.assertTrue(User.objects.filter(email=CREDENTIALS["email"]).exists())

    def test_register_duplicate_email_silent(self):
        User.objects.create_user(**CREDENTIALS)
        res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        # Same 202 + same body as a brand-new registration.
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(User.objects.filter(email=CREDENTIALS["email"]).count(), 1)

    def test_register_response_body_identical_for_new_and_duplicate(self):
        new_res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        dup_res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        self.assertEqual(new_res.status_code, dup_res.status_code)
        self.assertEqual(new_res.data, dup_res.data)

    def test_register_weak_password(self):
        res = self.client.post(REGISTER_URL, {"email": "a@b.com", "password": "123"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_email_format(self):
        res = self.client.post(
            REGISTER_URL, {"email": "not-an-email", "password": "StrongPass123!"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(**CREDENTIALS)

    def test_login_success(self):
        res = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_login_wrong_password(self):
        res = self.client.post(
            LOGIN_URL, {"email": CREDENTIALS["email"], "password": "wrong"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_unknown_email(self):
        res = self.client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": "whatever"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.access = login.data["access"]
        self.refresh = login.data["refresh"]

    def test_me_authenticated(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        res = self.client.get(ME_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], CREDENTIALS["email"])

    def test_me_unauthenticated_returns_401(self):
        res = self.client.get(ME_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        res = self.client.get(ME_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.access = login.data["access"]
        self.refresh = login.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_logout_blacklists_refresh(self):
        res = self.client.post(LOGOUT_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Using the same refresh token again should fail
        res2 = self.client.post(REFRESH_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_missing_refresh_returns_400(self):
        res = self.client.post(LOGOUT_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_requires_auth(self):
        self.client.credentials()
        res = self.client.post(LOGOUT_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class RefreshRotationTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.refresh = login.data["refresh"]

    def test_refresh_returns_new_token_pair(self):
        res = self.client.post(REFRESH_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        # Rotation enabled → response must include a new refresh token.
        self.assertIn("refresh", res.data)
        self.assertNotEqual(res.data["refresh"], self.refresh)

    def test_old_refresh_blacklisted_after_rotation(self):
        first = self.client.post(REFRESH_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        # Reusing the original refresh must fail — BLACKLIST_AFTER_ROTATION.
        replay = self.client.post(REFRESH_URL, {"refresh": self.refresh}, format="json")
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "rest_framework_simplejwt.authentication.JWTAuthentication",
        ),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 50,
        "DEFAULT_THROTTLE_RATES": {
            "user": "500/hour",
            "anon": "60/hour",
            "auth": "3/min",
            "claude_chat": "60/hour",
            "claude_scan": "20/hour",
        },
    }
)
class AnonAuthThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(**CREDENTIALS)

    def test_login_brute_force_returns_429(self):
        for _ in range(3):
            self.client.post(LOGIN_URL, {"email": "x@x.com", "password": "wrong"}, format="json")
        blocked = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
