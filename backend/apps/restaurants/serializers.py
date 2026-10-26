from django.contrib.auth import get_user_model
import re

from rest_framework import serializers

from .models import MembershipRole, Restaurant, RestaurantMembership
from .validators import CURRENCY_PATTERN

User = get_user_model()


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = fields


class MemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = RestaurantMembership
        fields = ("id", "user", "role", "is_active", "created_at")
        read_only_fields = fields


class PublicRestaurantSerializer(serializers.ModelSerializer):
    """Customer-facing restaurant details. Nothing internal: no members, no ids."""

    class Meta:
        model = Restaurant
        fields = (
            "slug", "name", "description", "contact_phone", "address", "currency", "timezone",
            "accepting_orders", "pickup_enabled", "dine_in_enabled", "requires_table_number",
        )
        read_only_fields = fields


class MemberCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=MembershipRole.choices, default=MembershipRole.STAFF)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=False, max_length=128, default="",
        help_text="Starting password for a new account. Ignored if the person already has an account.",
    )


class MemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=MembershipRole.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Send role and/or is_active.")
        return attrs


class RestaurantWriteSerializer(serializers.ModelSerializer):
    """Fields a restaurant is created with. Mirrors the database CHECK constraints."""

    currency = serializers.CharField(min_length=3, max_length=3)

    class Meta:
        model = Restaurant
        fields = (
            "name", "slug", "description", "contact_phone", "address", "currency", "timezone",
            "pickup_enabled", "dine_in_enabled", "requires_table_number",
        )

    def validate_currency(self, value):
        value = value.upper()
        if not re.fullmatch(CURRENCY_PATTERN, value):
            raise serializers.ValidationError("Use a 3-letter code such as USD.")
        return value

    def validate(self, attrs):
        current = self.instance

        def value(name, default):
            return attrs.get(name, getattr(current, name) if current else default)

        pickup = value("pickup_enabled", True)
        dine_in = value("dine_in_enabled", False)
        table = value("requires_table_number", False)
        errors = {}
        if not pickup and not dine_in:
            errors["pickup_enabled"] = "Enable at least one way for customers to order."
        if table and not dine_in:
            errors["requires_table_number"] = "Table numbers only apply when dine-in is enabled."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class RestaurantSettingsSerializer(RestaurantWriteSerializer):
    """Editable settings. The slug is shown but cannot change: it is part of public links."""

    class Meta(RestaurantWriteSerializer.Meta):
        fields = (*RestaurantWriteSerializer.Meta.fields, "accepting_orders")
        read_only_fields = ("slug",)
