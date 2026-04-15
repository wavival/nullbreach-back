"""
Critical auth tests:
  - register creates user and returns tokens
  - duplicate email is rejected
  - login returns tokens
  - wrong password is rejected
  - /me requires a valid token
  - logout blacklists the refresh token
"""
from django.contrib.auth import get_user_model
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
    def test_register_success(self):
        res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["email"], CREDENTIALS["email"])
        self.assertTrue(User.objects.filter(email=CREDENTIALS["email"]).exists())

    def test_register_duplicate_email(self):
        User.objects.create_user(**CREDENTIALS)
        res = self.client.post(REGISTER_URL, CREDENTIALS, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        res = self.client.post(REGISTER_URL, {"email": "a@b.com", "password": "123"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        User.objects.create_user(**CREDENTIALS)

    def test_login_success(self):
        res = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_login_wrong_password(self):
        res = self.client.post(LOGIN_URL, {"email": CREDENTIALS["email"], "password": "wrong"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_unknown_email(self):
        res = self.client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "whatever"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTests(APITestCase):
    def setUp(self):
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
