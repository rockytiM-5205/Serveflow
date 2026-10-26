import hashlib

from rest_framework.throttling import SimpleRateThrottle


class LoginIPThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginEmailThrottle(SimpleRateThrottle):
    """Limits guessing against one account regardless of the caller's IP."""

    scope = "login_email"

    def get_cache_key(self, request, view):
        data = request.data
        email = str(data.get("email", "")).strip().lower() if hasattr(data, "get") else ""
        if not email:
            return None
        digest = hashlib.sha256(email.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
