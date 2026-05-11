from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    """Validates registration payload WITHOUT exposing email uniqueness.

    The ModelSerializer auto-attached `UniqueValidator` on `email`, which
    returns "user with this email already exists" — that is an account-
    enumeration oracle. We validate format + password strength here and let
    the view handle duplicate-email collisions silently with a generic 202.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "date_joined")
        read_only_fields = fields


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
