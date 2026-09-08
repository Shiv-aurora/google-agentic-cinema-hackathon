"""Invite admission and browser-origin checks, separate from production keys."""
import os
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException


def invitation_required():
    return bool(os.getenv("CLAPPY_DEMO_ACCESS_KEY"))


def validate_access_settings():
    key = os.getenv("CLAPPY_DEMO_ACCESS_KEY", "")
    if key and len(key) < 32:
        raise ValueError("CLAPPY_DEMO_ACCESS_KEY must contain at least 32 characters")
    origin = os.getenv("CLAPPY_PUBLIC_ORIGIN", "")
    if origin:
        if not key:
            raise ValueError("A public origin requires CLAPPY_DEMO_ACCESS_KEY")
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("CLAPPY_PUBLIC_ORIGIN must be an HTTPS origin without a path")


def authorize_invitation(supplied):
    required = os.getenv("CLAPPY_DEMO_ACCESS_KEY", "")
    if required and not secrets.compare_digest(required.encode(), supplied.encode()):
        raise HTTPException(403, "Enter the demo invitation code to create a production.")


def origin_allowed(origin):
    # Non-browser clients still need an invitation or production bearer key.
    if not origin:
        return True
    configured = os.getenv("CLAPPY_PUBLIC_ORIGIN", "").rstrip("/")
    allowed = {configured} if configured else {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
    return origin in allowed
