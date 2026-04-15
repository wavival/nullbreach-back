"""
Critical chat tests:
  - create session
  - list sessions (only own sessions)
  - delete session
  - list messages
  - send message calls Claude and persists both sides
  - unauthenticated requests return 401
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.chat.models import ChatSession, Message

User = get_user_model()

LOGIN_URL = reverse("auth-login")
SESSIONS_URL = reverse("chat-sessions")

CREDENTIALS = {"email": "chat@example.com", "password": "StrongPass123!"}
OTHER_CREDENTIALS = {"email": "other@example.com", "password": "StrongPass123!"}


def session_detail_url(session_id):
    return reverse("chat-session-detail", args=[session_id])


def messages_url(session_id):
    return reverse("chat-messages", args=[session_id])


class ChatSessionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_create_session(self):
        res = self.client.post(SESSIONS_URL, {"title": "My session"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatSession.objects.filter(user=self.user).count(), 1)

    def test_list_sessions_returns_only_own(self):
        other = User.objects.create_user(**OTHER_CREDENTIALS)
        ChatSession.objects.create(user=self.user, title="Mine")
        ChatSession.objects.create(user=other, title="Not mine")
        res = self.client.get(SESSIONS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["title"], "Mine")

    def test_delete_session(self):
        session = ChatSession.objects.create(user=self.user)
        res = self.client.delete(session_detail_url(session.pk))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ChatSession.objects.filter(pk=session.pk).exists())

    def test_delete_other_users_session_returns_404(self):
        other = User.objects.create_user(**OTHER_CREDENTIALS)
        session = ChatSession.objects.create(user=other)
        res = self.client.delete(session_detail_url(session.pk))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        self.client.credentials()
        res = self.client.get(SESSIONS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MessageTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(**CREDENTIALS)
        login = self.client.post(LOGIN_URL, CREDENTIALS, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.session = ChatSession.objects.create(user=self.user)

    def test_list_messages_empty(self):
        res = self.client.get(messages_url(self.session.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, [])

    @patch("apps.chat.views.chat_completion", return_value="Here is my security advice.")
    def test_send_message_persists_both_and_returns_assistant(self, mock_claude):
        res = self.client.post(
            messages_url(self.session.pk),
            {"content": "How do I prevent XSS?"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["role"], "assistant")
        self.assertEqual(res.data["content"], "Here is my security advice.")

        messages = Message.objects.filter(session=self.session)
        self.assertEqual(messages.count(), 2)
        self.assertEqual(messages.filter(role="user").count(), 1)
        self.assertEqual(messages.filter(role="assistant").count(), 1)
        mock_claude.assert_called_once()

    @patch("apps.chat.views.chat_completion", return_value="Response.")
    def test_send_message_auto_titles_session(self, _mock):
        self.client.post(
            messages_url(self.session.pk),
            {"content": "Tell me about OWASP"},
            format="json",
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, "Tell me about OWASP")

    def test_send_message_to_other_session_returns_404(self):
        other = User.objects.create_user(**OTHER_CREDENTIALS)
        other_session = ChatSession.objects.create(user=other)
        res = self.client.post(
            messages_url(other_session.pk),
            {"content": "Trying to sneak in"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_messages_returns_in_order(self):
        Message.objects.create(session=self.session, role="user", content="first")
        Message.objects.create(session=self.session, role="assistant", content="second")
        res = self.client.get(messages_url(self.session.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)
        self.assertEqual(res.data[0]["content"], "first")
        self.assertEqual(res.data[1]["content"], "second")
