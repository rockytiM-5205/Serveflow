from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.authentication import CsrfSessionAuthentication, enforce_csrf

from apps.restaurants.services import check_password_strength

from .serializers import (
    ChangePasswordSerializer, LoginSerializer, OptionsSerializer, SessionSerializer, SignupSerializer, session_payload,
)
from .throttles import LoginEmailThrottle, LoginIPThrottle


class CsrfView(APIView):
    """Sets the csrftoken cookie. Call before login; send it back as X-CSRFToken."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={204: None}, summary="Set the CSRF cookie")
    def get(self, request):
        get_token(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    # Our auth class is listed so failures answer 401; anonymous callers pass through it.
    authentication_classes = [CsrfSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [LoginIPThrottle, LoginEmailThrottle]

    @extend_schema(request=LoginSerializer, responses=SessionSerializer, summary="Sign in")
    def post(self, request):
        enforce_csrf(request)  # login CSRF: anonymous requests are not checked by DRF itself
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # One message for unknown email, wrong password and inactive account.
            raise AuthenticationFailed("Invalid email or password.")
        login(request, user)  # rotates the session key and the CSRF token
        return Response(session_payload(user))


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None}, summary="Sign out")
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses=SessionSerializer, summary="Current user and restaurant memberships")
    def get(self, request):
        return Response(session_payload(request.user))


class OptionsView(APIView):
    """What the sign-in page needs to know before anyone is signed in."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=OptionsSerializer, summary="Public sign-in options")
    def get(self, request):
        return Response({"self_service": settings.SELF_SERVICE})


class SignupView(APIView):
    authentication_classes = [CsrfSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    @extend_schema(request=SignupSerializer, responses={201: SessionSerializer}, summary="Create an account (self-service only)")
    def post(self, request):
        if not settings.SELF_SERVICE:
            raise PermissionDenied("Creating accounts here is turned off.", code="signup_disabled")
        enforce_csrf(request)
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        User = get_user_model()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    data["email"], data["password"], first_name=data["first_name"], last_name=data["last_name"]
                )
        except IntegrityError:
            raise ValidationError({"email": ["An account with this email already exists."]}) from None
        login(request, user)
        return Response(session_payload(user), status=status.HTTP_201_CREATED)


class ChangePasswordView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_change"

    @extend_schema(request=ChangePasswordSerializer, responses={204: None}, summary="Change your password")
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": ["Incorrect password."]})
        check_password_strength(serializer.validated_data["new_password"], user, field="new_password")
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)  # keep this session signed in; others end
        return Response(status=status.HTTP_204_NO_CONTENT)
