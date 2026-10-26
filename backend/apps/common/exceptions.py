"""One error shape for every API error: {"error": {"code", "message", "details"}}."""
from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler

class Conflict(exceptions.APIException):
    """409: the request is valid but clashes with the current state of the resource."""

    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"

    def __init__(self, detail=None, code=None, details=None):
        super().__init__(detail, code)
        self.details = details


class BadRequest(exceptions.APIException):
    """400 for a malformed request that is not a field validation problem."""

    status_code = 400
    default_detail = "The request was malformed."
    default_code = "bad_request"


_CODES = (
    (Conflict, "conflict"),
    (BadRequest, "bad_request"),
    (exceptions.NotAuthenticated, "not_authenticated"),
    (exceptions.AuthenticationFailed, "authentication_failed"),
    (exceptions.PermissionDenied, "permission_denied"),
    (exceptions.NotFound, "not_found"),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.Throttled, "throttled"),
    (exceptions.ParseError, "malformed_request"),
    (exceptions.UnsupportedMediaType, "unsupported_media_type"),
    (exceptions.NotAcceptable, "not_acceptable"),
)


def error_body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unexpected errors stay 500s; nothing internal is leaked

    if isinstance(exc, exceptions.ValidationError):
        response.data = error_body("validation_error", "The request was invalid.", response.data)
        return response

    code = next((c for cls, c in _CODES if isinstance(exc, cls)), "error")
    # A view may raise e.g. PermissionDenied("...", code="insufficient_role").
    specific = exc.get_codes()
    if isinstance(specific, str) and specific != getattr(exc, "default_code", None):
        code = specific
    message = str(exc.detail)
    if message.startswith("CSRF Failed"):
        code = "csrf_failed"
    response.data = error_body(code, message, getattr(exc, "details", None))
    return response
