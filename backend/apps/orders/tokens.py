"""Customer order links: <order uuid, 32 hex><HMAC, 64 hex>.

The signature covers the uuid and the order's token_version, so a link cannot be forged
or guessed, and raising token_version revokes it. Nothing about the token is stored.
Because it derives from SECRET_KEY, rotating the key invalidates old links unless the old
key is kept in SECRET_KEY_FALLBACKS.
"""
import hmac
import re
import uuid

from django.conf import settings
from django.utils.crypto import salted_hmac

SALT = "serveflow.order-token.v1"
_FORMAT = re.compile(r"^[0-9a-f]{96}$")


def _signature(public_id, version, secret):
    return salted_hmac(SALT, f"{public_id.hex}:{version}", secret=secret, algorithm="sha256").hexdigest()


def make_token(order):
    return order.public_id.hex + _signature(order.public_id, order.token_version, settings.SECRET_KEY)


def parse_token(token):
    """The order uuid inside a well-formed token, else None."""
    if not isinstance(token, str) or not _FORMAT.fullmatch(token):
        return None
    return uuid.UUID(token[:32])


def verify_token(token, order):
    supplied = token[32:]
    secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return any(hmac.compare_digest(supplied, _signature(order.public_id, order.token_version, s)) for s in secrets)
