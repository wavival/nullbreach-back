import anthropic
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .claude import chat_completion
from .models import ChatSession, Message
from .serializers import ChatSessionSerializer, MessageSerializer, SendMessageSerializer


class ChatSessionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ChatSessionSerializer(many=True)},
        summary="List all chat sessions for the authenticated user",
        tags=["chat"],
    )
    def get(self, request):
        sessions = ChatSession.objects.filter(user=request.user)
        return Response(ChatSessionSerializer(sessions, many=True).data)

    @extend_schema(
        request=ChatSessionSerializer,
        responses={201: ChatSessionSerializer},
        summary="Create a new chat session",
        tags=["chat"],
    )
    def post(self, request):
        serializer = ChatSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        session = serializer.save(user=request.user)
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_session(self, request, session_id):
        try:
            return ChatSession.objects.get(pk=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return None

    @extend_schema(
        responses={204: OpenApiResponse(description="Session deleted")},
        summary="Delete a chat session",
        tags=["chat"],
    )
    def delete(self, request, session_id):
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_session(self, request, session_id):
        try:
            return ChatSession.objects.get(pk=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return None

    @extend_schema(
        responses={200: MessageSerializer(many=True)},
        summary="List all messages in a session",
        tags=["chat"],
    )
    def get(self, request, session_id):
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        messages = session.messages.all()
        return Response(MessageSerializer(messages, many=True).data)

    @extend_schema(
        request=SendMessageSerializer,
        responses={201: MessageSerializer},
        summary="Send a message — calls Claude and returns the assistant reply",
        tags=["chat"],
    )
    def post(self, request, session_id):
        session = self._get_session(request, session_id)
        if session is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_content = serializer.validated_data["content"]

        # Persist user message
        Message.objects.create(session=session, role=Message.Role.USER, content=user_content)

        # Build history for Claude
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in session.messages.all()
        ]

        try:
            assistant_content = chat_completion(history)
        except anthropic.APIError as exc:
            return Response(
                {"detail": f"Claude API error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Persist assistant message
        assistant_message = Message.objects.create(
            session=session,
            role=Message.Role.ASSISTANT,
            content=assistant_content,
        )

        # Auto-title the session from the first user message
        if not session.title and session.messages.count() <= 2:
            session.title = user_content[:80]
            session.save(update_fields=["title", "updated_at"])

        return Response(MessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)
