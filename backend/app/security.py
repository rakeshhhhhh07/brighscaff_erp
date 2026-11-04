"""JWT issuing/verification and the decorators that guard protected endpoints.

Tokens are signed with HMAC-SHA256 using the app ``SECRET_KEY``. The implementation is
deliberately small and dependency-free: a JWT is three base64url segments joined by dots,
``header.payload.signature``, and verifying one is a constant-time compare of the signature
plus an expiry check.

Usage
-----
    @blp.route("/thing")
    class Thing(MethodView):
        @login_required
        def get(self):
            return {"you_are": g.current_user["username"]}

        @roles_required("ADMIN")
        def delete(self):
            ...
"""

import base64
import hashlib
import hmac
import json
import time
from functools import wraps

from flask import current_app, g, request
from flask_smorest import abort
from sqlalchemy import text

from . import db

# Access tokens are short-lived so a leaked token stops working quickly; the
# frontend simply asks the user to sign in again when one expires.
TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12 hours
ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# base64url helpers (JWT uses the URL-safe alphabet with padding stripped)
# ---------------------------------------------------------------------------


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(segment: str) -> bytes:
    # Re-add the padding that encoding stripped; len must be a multiple of 4.
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def secret_key() -> bytes:
    return current_app.config["SECRET_KEY"].encode("utf-8")


def sign(signing_input: bytes) -> str:
    return b64url_encode(hmac.new(secret_key(), signing_input, hashlib.sha256).digest())


# ---------------------------------------------------------------------------
# Issue / verify
# ---------------------------------------------------------------------------


def create_access_token(user, ttl_seconds=TOKEN_TTL_SECONDS):
    """Sign a JWT carrying the user's identity and role."""
    issued_at = int(time.time())
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": int(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name") or user["username"],
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }
    segments = [
        b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(sign(signing_input))
    return ".".join(segments), payload["exp"]


def decode_access_token(token):
    """Return the payload of a valid token, or ``None`` if it is unusable.

    A token is rejected when it is malformed, signed with the wrong key, or expired.
    """
    try:
        header_b64, payload_b64, signature = token.split(".")
    except (ValueError, AttributeError):
        return None

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    # compare_digest avoids leaking signature bytes through timing.
    if not hmac.compare_digest(sign(signing_input), signature):
        return None

    try:
        payload = json.loads(b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def bearer_token():
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return header[len(prefix) :].strip() if header.startswith(prefix) else None


def load_user(user_id):
    row = db.session.execute(
        text(
            """SELECT id, username, full_name, email, role, is_active, must_change_password
            FROM app_users WHERE id=:id"""
        ),
        {"id": user_id},
    ).fetchone()
    return dict(row._mapping) if row else None


def current_user():
    """The authenticated user for this request, or ``None``."""
    return getattr(g, "current_user", None)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def authenticate():
    """Resolve the bearer token to a live, active user and stash it on ``g``."""
    token = bearer_token()
    if not token:
        abort(401, message="Sign in to continue")
    payload = decode_access_token(token)
    if not payload:
        abort(401, message="Session expired, please sign in again")
    user = load_user(payload["sub"])
    if not user:
        abort(401, message="Account no longer exists")
    # Deactivating a user takes effect immediately, even on an unexpired token.
    if not user["is_active"]:
        abort(403, message="This account has been deactivated")
    g.current_user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        authenticate()
        return view(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    """Restrict a view to the given roles. Implies ``login_required``."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = authenticate()
            if user["role"] not in roles:
                abort(403, message="You do not have permission to do that")
            return view(*args, **kwargs)

        return wrapper

    return decorator
