from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Request


AUTH_COOKIE_NAME = "gea_workshop_auth"
DEFAULT_COOKIE_MAX_AGE = 60 * 60 * 8


def auth_password() -> str:
    return os.getenv("APP_PASSWORD", "")


def auth_secret_key() -> str:
    return os.getenv("APP_SECRET_KEY", "")


def auth_enabled() -> bool:
    return bool(auth_password())


def assert_auth_config() -> None:
    production = os.getenv("K_SERVICE") or os.getenv("APP_ENV", "").lower() == "production"
    if not production:
        return
    if not auth_password():
        raise RuntimeError(
            "APP_PASSWORD is required when running on Cloud Run or APP_ENV=production."
        )
    if not auth_secret_key():
        raise RuntimeError(
            "APP_SECRET_KEY is required when running on Cloud Run or APP_ENV=production."
        )


def cookie_max_age() -> int:
    value = os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", str(DEFAULT_COOKIE_MAX_AGE))
    try:
        return max(60, int(value))
    except ValueError:
        return DEFAULT_COOKIE_MAX_AGE


def create_auth_cookie(now: Optional[int] = None) -> str:
    issued_at = int(now or time.time())
    payload = str(issued_at)
    signature = _sign(payload)
    token = f"{payload}.{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def request_is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        return False
    return validate_auth_cookie(cookie)


def validate_auth_cookie(cookie: str, now: Optional[int] = None) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(cookie.encode("ascii")).decode("utf-8")
        issued_at_text, signature = decoded.rsplit(".", 1)
        issued_at = int(issued_at_text)
    except (ValueError, UnicodeDecodeError):
        return False

    if not hmac.compare_digest(signature, _sign(issued_at_text)):
        return False

    age = int(now or time.time()) - issued_at
    return 0 <= age <= cookie_max_age()


def password_matches(candidate: str) -> bool:
    password = auth_password()
    return bool(password) and hmac.compare_digest(candidate, password)


def _sign(payload: str) -> str:
    secret = auth_secret_key() or auth_password()
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
