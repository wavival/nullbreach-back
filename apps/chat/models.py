from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            # Covers the canonical "list my sessions, newest first" query.
            models.Index(fields=["user", "-updated_at"], name="chat_sess_user_upd_idx"),
        ]

    def __str__(self):
        return f"Session {self.pk} — {self.user.email}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            # Speeds up the history scan in MessageListCreateView.post
            # (ordering by created_at within a session).
            models.Index(fields=["session", "created_at"], name="chat_msg_sess_created_idx"),
        ]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"
