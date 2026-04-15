from rest_framework import serializers

from .models import ChatSession, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("id", "role", "content", "created_at")
        read_only_fields = ("id", "role", "created_at")


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = ChatSession
        fields = ("id", "title", "message_count", "created_at", "updated_at")
        read_only_fields = ("id", "message_count", "created_at", "updated_at")


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=32_000)
