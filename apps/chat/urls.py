from django.urls import path

from .views import ChatSessionDetailView, ChatSessionListCreateView, MessageListCreateView

urlpatterns = [
    path("sessions/", ChatSessionListCreateView.as_view(), name="chat-sessions"),
    path("sessions/<int:session_id>/", ChatSessionDetailView.as_view(), name="chat-session-detail"),
    path("sessions/<int:session_id>/messages/", MessageListCreateView.as_view(), name="chat-messages"),
]
