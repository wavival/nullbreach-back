from rest_framework import serializers

from .models import ChatSession, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("id", "role", "content", "created_at")
        read_only_fields = ("id", "role", "created_at")


class ChatSessionSerializer(serializers.ModelSerializer):
    # `message_count` is provided by the view's queryset annotation
    # (Count("messages")) — avoids one COUNT(*) per session on list endpoints.
    message_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ChatSession
        fields = ("id", "title", "message_count", "created_at", "updated_at")
        read_only_fields = ("id", "message_count", "created_at", "updated_at")


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=32_000)
