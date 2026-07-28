from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, Unauthorized
from sanic.response import json
from sqlalchemy import select

from .models import AuditEvent, PasswordSetupToken, User
from .schemas import PasswordChange, PasswordSet
from .security import (
    DUMMY_PASSWORD_HASH,
    SESSION_COOKIE,
    check_rate_limit,
    clear_rate_limit,
    hash_password,
    issue_session,
    login_required,
    normalize_email_address,
    verify_password,
)

auth_bp = Blueprint("auth", url_prefix="/api/v1/auth")


def setup_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_json(user: User) -> dict:
    return {
        "id": str(user.id),
        "email_address": user.email_address,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
    }


@auth_bp.post("/login")
async def login(request: Request):
    payload = request.json or {}
    email_address = str(payload.get("email_address", "")).strip()
    password = str(payload.get("password", ""))
    if not email_address or not password:
        raise InvalidUsage("Email address and password are required")
    normalized = normalize_email_address(email_address)
    check_rate_limit(
        request,
        namespace="login",
        identity=normalized,
        limit=request.app.ctx.settings.login_rate_limit,
    )
    authenticated = False
    user: User | None = None
    async with request.app.ctx.db.session() as db:
        user = await db.scalar(
            select(User).where(User.normalized_email_address == normalized)
        )
        password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
        authenticated = bool(user and user.active and verify_password(password, password_hash))
        db.add(
            AuditEvent(
                actor_id=user.id if authenticated and user else None,
                action="auth.login_succeeded" if authenticated else "auth.login_failed",
                entity_type="user" if authenticated else "login",
                entity_id=(
                    str(user.id)
                    if authenticated and user
                    else hashlib.sha256(normalized.encode()).hexdigest()
                ),
                reason=None if authenticated else "Invalid credentials",
                request_id=request.ctx.request_id,
            )
        )
        if authenticated and user:
            user.last_login_at = datetime.now(UTC)
    if not authenticated or not user:
        raise Unauthorized("Username or password is incorrect")

    clear_rate_limit(request, namespace="login", identity=normalized)
    csrf_token = secrets.token_urlsafe(32)
    response = json(
        {
            "signed_in": True,
            "user": user_json(user),
            "csrf_token": csrf_token,
        }
    )
    response.add_cookie(
        SESSION_COOKIE,
        issue_session(user, request.app.ctx.settings, csrf_token),
        httponly=True,
        secure=request.app.ctx.settings.secure_cookies,
        samesite="Lax",
        max_age=request.app.ctx.settings.session_max_age_seconds,
        path="/",
    )
    return response


@auth_bp.post("/logout")
@login_required()
async def logout(request: Request):
    async with request.app.ctx.db.session() as db:
        db.add(
            AuditEvent(
                actor_id=request.ctx.user.id,
                action="auth.logout",
                entity_type="user",
                entity_id=str(request.ctx.user.id),
                request_id=request.ctx.request_id,
            )
        )
    response = json({"signed_out": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@auth_bp.get("/me")
@login_required()
async def me(request: Request):
    return {
        **user_json(request.ctx.user),
        "csrf_token": request.ctx.session_data["csrf_token"],
    }


async def valid_setup_token(request: Request, token: str, *, lock: bool = False):
    query = (
        select(PasswordSetupToken, User)
        .join(User, PasswordSetupToken.user_id == User.id)
        .where(
            PasswordSetupToken.token_hash == setup_token_hash(token),
            PasswordSetupToken.used_at.is_(None),
            PasswordSetupToken.expires_at > datetime.now(UTC),
            User.active.is_(True),
        )
    )
    if lock:
        query = query.with_for_update()
    async with request.app.ctx.db.session() as db:
        return await db.execute(query)


@auth_bp.get("/password-setup/<token:str>")
async def password_setup_details(request: Request, token: str):
    result = await valid_setup_token(request, token)
    row = result.one_or_none()
    if not row:
        raise InvalidUsage("This invitation is invalid or expired")
    _setup_token, user = row
    return {"email_address": user.email_address, "full_name": user.full_name}


@auth_bp.post("/password-setup/<token:str>")
async def set_password(request: Request, token: str):
    payload = PasswordSet.model_validate(request.json or {})
    now = datetime.now(UTC)
    async with request.app.ctx.db.session() as db:
        row = (
            await db.execute(
                select(PasswordSetupToken, User)
                .join(User, PasswordSetupToken.user_id == User.id)
                .where(
                    PasswordSetupToken.token_hash == setup_token_hash(token),
                    PasswordSetupToken.used_at.is_(None),
                    PasswordSetupToken.expires_at > now,
                    User.active.is_(True),
                )
                .with_for_update()
            )
        ).one_or_none()
        if not row:
            raise InvalidUsage("This invitation is invalid or expired")
        setup_token, user = row
        user.password_hash = hash_password(payload.password)
        user.session_version += 1
        setup_token.used_at = now
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="auth.password_set",
                entity_type="user",
                entity_id=str(user.id),
                request_id=request.ctx.request_id,
            )
        )
    return {"password_set": True}


@auth_bp.post("/password")
@login_required()
async def change_password(request: Request):
    payload = PasswordChange.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        user = await db.get(User, request.ctx.user.id)
        if not user or not verify_password(payload.current_password, user.password_hash):
            raise Unauthorized("Current password is incorrect")
        user.password_hash = hash_password(payload.password)
        user.session_version += 1
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="auth.password_changed",
                entity_type="user",
                entity_id=str(user.id),
                request_id=request.ctx.request_id,
            )
        )
    response = json({"password_changed": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
