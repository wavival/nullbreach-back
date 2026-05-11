from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.throttles import AuthAnonThrottle

from .serializers import LogoutSerializer, RegisterSerializer, UserSerializer

User = get_user_model()

GENERIC_REGISTER_RESPONSE = {
    "detail": "Registration accepted. If this email is new, your account is now active.",
}


class RegisterView(APIView):
    """Register a new user without leaking account existence.

    On success and on duplicate-email we return the same generic 202 with no
    body differences and no tokens — this prevents an unauthenticated attacker
    from enumerating registered emails. Genuine new users obtain tokens by
    POSTing to `/api/auth/login/` immediately after registration.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonThrottle]

    @extend_schema(
        request=RegisterSerializer,
        responses={202: OpenApiResponse(description="Registration accepted")},
        summary="Register a new user (silent on duplicate email)",
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Swallow duplicate-email IntegrityError so the response shape is
        # identical whether the email was new or already registered. The
        # `atomic()` savepoint keeps the surrounding test transaction (and any
        # outer atomic block) usable after the rollback.
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            pass

        return Response(GENERIC_REGISTER_RESPONSE, status=status.HTTP_202_ACCEPTED)


@extend_schema(tags=["auth"], summary="Login — returns access + refresh tokens")
class LoginView(TokenObtainPairView):
    """Exchange email+password for an access/refresh JWT pair.

    Rate-limited by IP via `AuthAnonThrottle` to slow credential stuffing.
    SimpleJWT's underlying serializer returns 401 for both wrong-password and
    unknown-email — no user enumeration possible here.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonThrottle]


@extend_schema(tags=["auth"], summary="Refresh access token")
class RefreshView(TokenRefreshView):
    """Rotate a refresh token into a fresh access+refresh pair.

    With `BLACKLIST_AFTER_ROTATION=True`, presenting the same refresh token
    twice fails — second use returns 401.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthAnonThrottle]


class LogoutView(APIView):
    """Blacklist the supplied refresh token so it can no longer rotate.

    Access tokens are stateless and remain valid until expiry (15 min); the
    frontend should drop them client-side on logout.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        responses={204: OpenApiResponse(description="Logged out")},
        summary="Logout — blacklists the refresh token",
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Return the authenticated user's public profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: UserSerializer},
        summary="Authenticated user info",
        tags=["auth"],
    )
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
