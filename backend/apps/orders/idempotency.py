"""Idempotency-Key handling: a retry returns the original answer instead of repeating the action."""
import hashlib
import json
import re

from rest_framework.response import Response

from apps.common.exceptions import BadRequest, Conflict

from .models import IdempotencyKey

_KEY = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def read_key(request):
    key = request.headers.get("Idempotency-Key", "")
    if not _KEY.fullmatch(key):
        raise BadRequest(
            "Send a unique Idempotency-Key header: 16 to 64 letters, digits, '-' or '_'.",
            code="idempotency_key_required",
        )
    return key


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def find_replay(restaurant, scope, key, request_hash):
    """The stored answer for this key, None if the key is new. The same key with a different
    request is a client bug and is refused rather than silently answered."""
    stored = IdempotencyKey.objects.filter(restaurant=restaurant, scope=scope, key=key).first()
    if stored is None:
        return None
    if stored.request_hash != request_hash:
        raise Conflict("This Idempotency-Key was already used for a different request.", code="idempotency_key_reused")
    return stored


def remember(restaurant, scope, key, request_hash, status, body):
    return IdempotencyKey.objects.create(
        restaurant=restaurant, scope=scope, key=key, request_hash=request_hash, response_status=status, response_body=body
    )


def replay_response(stored):
    return Response(stored.response_body, status=stored.response_status, headers={"Idempotent-Replay": "true"})
