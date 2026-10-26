"""Session authentication for the staff dashboard."""
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication


class CsrfSessionAuthentication(SessionAuthentication):
    """Session auth that enforces CSRF for signed-in users.

    Plain SessionAuthentication has no authenticate header, so DRF answers
    unauthenticated requests with 403. Returning a header here makes it 401.
    """

    def authenticate_header(self, request):
        return "Session"


def enforce_csrf(request):
    """Run the CSRF check on a request whose user is not yet authenticated (login)."""
    CsrfSessionAuthentication().enforce_csrf(request)


class CsrfSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.common.authentication.CsrfSessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
