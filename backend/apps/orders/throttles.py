import hashlib
import re

from rest_framework.throttling import SimpleRateThrottle


class OrderPhoneThrottle(SimpleRateThrottle):
    """Caps orders per phone number per restaurant, whatever IP they come from."""

    scope = "order_phone"

    def get_cache_key(self, request, view):
        data = request.data
        phone = re.sub(r"\D", "", str(data.get("customer_phone", ""))) if hasattr(data, "get") else ""
        if not phone:
            return None
        ident = hashlib.sha256(f"{view.kwargs.get('slug')}:{phone}".encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}
