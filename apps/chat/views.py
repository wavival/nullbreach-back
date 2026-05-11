from django.db import transaction
from django.db.models import Count

import anthropic
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.claude_errors import handle_claude_error
from apps.throttles import ClaudeChatThrottle

from .claude import MAX_HISTORY_MESSAGES, chat_completion
from .models import ChatSession, Message
from .serializers import ChatSessionSerializer, MessageSerializer, SendMessageSerializer


class ChatSessionListCreateView(GenericAPIView):
    """List or create chat sessions owned by the authenticated user.

    The list endpoint annotates `message_count` in SQL (one COUNT(*) total)
    rather than emitting one query per session.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ChatSessionSerializer

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).annotate(
            message_count=Count("messages")
        )

    @extend_schema(
        responses={200: ChatSessionSerializer(many=True)},
        summary="List all chat sessions for the authenticated user",
        tags=["chat"],
    )
    def get(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        serializer = ChatSessionSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=ChatSessionSerializer,
        responses={201: ChatSessionSerializer},
        summary="Create a new chat session",
        tags=["chat"],
    )
    def post(self, request: Request) -> Response:
        serializer = ChatSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        session = serializer.save(user=request.user)
        # Re-fetch with annotation so message_count is present in the response.
        session = self.get_queryset().get(pk=session.pk)
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class ChatSessionDetailView(APIView):
    """Retrieve, rename, or delete a single chat session.

    Cross-user access is suppressed by filtering on `user=request.user` and
    returning 404 (never 403) so existence of other users' sessions is not
    leaked.
    """

    permission_classes = [IsAuthenticated]

    def _get_session(self, request: Request, session_id: int):
        try:
            return ChatSession.objects.annotate(message_count=Count("messages")).get(
                pk=session_id, user=request.user
            )
        except ChatSession.DoesNotExist:
            return None

    @extend_schema(
        responses={204: OpenApiResponse(description="Session deleted")},
        summary="Delete a chat session",
        tags=["chat"],
    )
    def delete(self, request: Request, session_id: int) -> Response:
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=ChatSessionSerializer,
        responses={200: ChatSessionSerializer},
        summary="Update a chat session (e.g. rename title)",
        tags=["chat"],
    )
    def patch(self, request: Request, session_id: int) -> Response:
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ChatSessionSerializer(session, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class MessageListCreateView(GenericAPIView):
    """List messages in a session or send a new one through Claude.

    POST persists user + assistant messages in a single transaction so a
    Claude failure cannot leave an orphaned user message; only POST is
    metered by `ClaudeChatThrottle` (GET is cheap and uses the global rate).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_throttles(self):
        if self.request.method == "POST":
            return [ClaudeChatThrottle()]
        return super().get_throttles()

    def _get_session(self, request: Request, session_id: int):
        try:
            return ChatSession.objects.get(pk=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return None

    @extend_schema(
        responses={200: MessageSerializer(many=True)},
        summary="List all messages in a session",
        tags=["chat"],
    )
    def get(self, request: Request, session_id: int) -> Response:
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        page = self.paginate_queryset(session.messages.all())
        serializer = MessageSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=SendMessageSerializer,
        responses={201: MessageSerializer},
        summary="Send a message — calls Claude and returns the assistant reply",
        tags=["chat"],
    )
    def post(self, request: Request, session_id: int) -> Response:
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_content = serializer.validated_data["content"]

        # Cap replayed history to bound token cost and prevent O(n²) growth.
        # Order by -created_at so we get the LAST N, then reverse to chronological.
        prior = list(
            session.messages.order_by("-created_at").values("role", "content")[
                : MAX_HISTORY_MESSAGES - 1
            ]
        )
        history = list(reversed(prior)) + [{"role": Message.Role.USER, "content": user_content}]

        try:
            assistant_content = chat_completion(history)
        except anthropic.APIError as exc:
            return handle_claude_error(exc)

        # Persist user + assistant atomically so a Claude failure does not
        # leave an orphaned user message in the session.
        with transaction.atomic():
            is_first_message = not session.messages.exists()
            Message.objects.create(session=session, role=Message.Role.USER, content=user_content)
            assistant_message = Message.objects.create(
                session=session,
                role=Message.Role.ASSISTANT,
                content=assistant_content,
            )
            if is_first_message and not session.title:
                session.title = user_content[:80]
                session.save(update_fields=["title", "updated_at"])

        return Response(MessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)
