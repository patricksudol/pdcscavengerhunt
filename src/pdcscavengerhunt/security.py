from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
from collections import deque
from datetime import UTC, datetime
from functools import wraps
from typing import Any
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sanic import Request
from sanic.exceptions import Forbidden, SanicException, Unauthorized
from sqlalchemy import select

from .models import User
from .settings import Settings

PASSWORD_ALGORITHM = "scrypt"
SESSION_COOKIE = "pdc_hunt_session"


def normalize_email_address(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def normalize_code(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().upper()


def fingerprint_code(value: str, settings: Settings) -> str:
    return hmac.new(
        settings.clue_code_secret.encode(),
        normalize_code(value).encode(),
        hashlib.sha256,
    ).hexdigest()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{PASSWORD_ALGORITHM}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


DUMMY_PASSWORD_HASH = hash_password("not-a-real-password", salt=b"\0" * 16)


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="pdc-scavenger-session")


def issue_session(user: User, settings: Settings, csrf_token: str) -> str:
    return _serializer(settings).dumps(
        {
            "id": str(user.id),
            "version": user.session_version,
            "csrf_token": csrf_token,
        }
    )


def read_session(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        return _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


async def current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized("Sign-in required")
    session_data = read_session(token, request.app.ctx.settings)
    if not session_data:
        raise Unauthorized("Your session has expired")
    request.ctx.session_data = session_data
    try:
        user_id = UUID(session_data["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise Unauthorized("Your session is invalid") from error
    async with request.app.ctx.db.session() as db:
        user = await db.scalar(select(User).where(User.id == user_id))
        if (
            not user
            or not user.active
            or session_data.get("version") != user.session_version
        ):
            raise Unauthorized("Your account is inactive")
        return user


def require_csrf(request: Request) -> None:
    expected = request.ctx.session_data.get("csrf_token", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise Forbidden("Invalid CSRF token")


def login_required(*, admin: bool = False):
    def decorator(handler):
        @wraps(handler)
        async def wrapped(request: Request, *args: Any, **kwargs: Any):
            user = await current_user(request)
            if admin and not user.is_admin:
                raise Forbidden("Administrator access required")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_csrf(request)
            request.ctx.user = user
            return await handler(request, *args, **kwargs)

        return wrapped

    return decorator


def check_rate_limit(
    request: Request,
    *,
    namespace: str,
    identity: str,
    limit: int,
) -> None:
    key = hashlib.sha256(f"{namespace}\0{request.ip}\0{identity}".encode()).hexdigest()
    attempts: deque[datetime] = request.app.ctx.rate_limits[key]
    now = datetime.now(UTC)
    cutoff = now.timestamp() - request.app.ctx.settings.rate_limit_window_seconds
    while attempts and attempts[0].timestamp() < cutoff:
        attempts.popleft()
    if len(attempts) >= limit:
        raise SanicException("Too many attempts. Try again later.", status_code=429)
    attempts.append(now)


def clear_rate_limit(request: Request, *, namespace: str, identity: str) -> None:
    key = hashlib.sha256(f"{namespace}\0{request.ip}\0{identity}".encode()).hexdigest()
    request.app.ctx.rate_limits.pop(key, None)
