from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.restaurants.models import RestaurantMembership
from apps.restaurants.services import can_create_restaurant, check_password_strength

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = fields


class RestaurantSummarySerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class MembershipSummarySerializer(serializers.ModelSerializer):
    restaurant = RestaurantSummarySerializer(read_only=True)

    class Meta:
        model = RestaurantMembership
        fields = ("restaurant", "role")
        read_only_fields = fields


class SessionSerializer(serializers.Serializer):
    user = UserSerializer()
    memberships = MembershipSummarySerializer(many=True)
    can_create_restaurant = serializers.BooleanField()


class OptionsSerializer(serializers.Serializer):
    self_service = serializers.BooleanField()


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"])
        check_password_strength(attrs["password"], candidate)
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


def session_payload(user):
    """The signed-in user plus the restaurants they can currently operate."""
    memberships = (
        RestaurantMembership.objects.select_related("restaurant")
        .filter(user=user, is_active=True, restaurant__is_active=True)
        .order_by("restaurant__name", "id")
    )
    return SessionSerializer(
        {"user": user, "memberships": memberships, "can_create_restaurant": can_create_restaurant(user)}
    ).data
