from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from pydantic import ValidationError
from sanic import Request, Sanic
from sanic.exceptions import SanicException
from sanic.log import logger
from sanic.response import file, json
from sqlalchemy import text

from .admin import admin_bp
from .auth import auth_bp
from .cloudflare_media import CloudflareMediaProvider
from .db import Database
from .media import media_bp
from .player import player_bp
from .settings import Settings, get_settings


def operational_log_path(path: str) -> str:
    password_setup_prefix = "/api/v1/auth/password-setup/"
    if path.startswith(password_setup_prefix):
        return f"{password_setup_prefix}<redacted>"
    return path


def create_app(
    settings: Settings | None = None, *, name: str = "PDCScavengerHunt"
) -> Sanic:
    settings = settings or get_settings()
    app = Sanic(name)
    app.config.FALLBACK_ERROR_FORMAT = "json"
    app.config.REQUEST_MAX_SIZE = (
        max(settings.photo_max_bytes, settings.video_max_bytes) + 1024 * 1024
    )
    app.ctx.settings = settings
    app.ctx.db = Database(settings.database_url)
    app.ctx.media = CloudflareMediaProvider(settings)
    app.ctx.rate_limits = defaultdict(deque)
    app.blueprint(auth_bp)
    app.blueprint(player_bp)
    app.blueprint(admin_bp)
    app.blueprint(media_bp)

    @app.middleware("request")
    async def request_context(request: Request) -> None:
        request.ctx.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.ctx.request_started_at = time.perf_counter()

    @app.middleware("response")
    async def normalize_response(request: Request, response):
        if isinstance(response, tuple):
            body, status = response
            response = json(body, status=status)
        elif isinstance(response, (dict, list)):
            response = json(response)
        response.headers["X-Request-ID"] = request.ctx.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        is_media_frame = (
            request.method == "GET"
            and request.path.startswith("/api/v1/media/")
            and request.path != "/api/v1/media/cloudflare-stream/webhook"
        )
        response.headers["X-Frame-Options"] = (
            "SAMEORIGIN" if is_media_frame else "DENY"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.environment == "production":
            frame_ancestors = "'self'" if is_media_frame else "'none'"
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "base-uri 'self'; "
                "connect-src 'self'; "
                "font-src 'self' https://fonts.gstatic.com; "
                "form-action 'self'; "
                f"frame-ancestors {frame_ancestors}; "
                "frame-src 'self' https://*.cloudflarestream.com "
                "https://*.videodelivery.net; "
                "img-src 'self' data: https://*.r2.cloudflarestorage.com; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
            )
        if request.path.startswith("/api/") and request.path not in {
            "/api/health",
            "/api/ready",
        }:
            duration_ms = (
                time.perf_counter() - request.ctx.request_started_at
            ) * 1000
            user = getattr(request.ctx, "user", None)
            log = logger.warning if response.status >= 400 else logger.info
            log(
                "event=http_request request_id=%s method=%s path=%s "
                "status=%s duration_ms=%.1f user_id=%s",
                request.ctx.request_id,
                request.method,
                operational_log_path(request.path),
                response.status,
                duration_ms,
                getattr(user, "id", "-"),
            )
        return response

    @app.exception(ValidationError)
    async def validation_error(_request: Request, error: ValidationError):
        return json(
            {
                "error": "validation_error",
                "message": "Please check the highlighted fields",
                "details": error.errors(include_url=False, include_context=False),
            },
            status=422,
        )

    @app.exception(SanicException)
    async def sanic_error(_request: Request, error: SanicException):
        return json(
            {"error": error.__class__.__name__, "message": str(error)},
            status=error.status_code,
        )

    @app.get("/api/health")
    async def health(_request: Request):
        return {"status": "ok"}

    @app.get("/api/ready")
    async def ready(_request: Request):
        try:
            async with app.ctx.db.session() as db:
                await db.execute(text("SELECT 1"))
            return {"status": "ready"}
        except Exception:
            return json({"status": "unavailable"}, status=503)

    frontend = Path(settings.frontend_dist)
    if frontend.exists():
        app.static("/assets", frontend / "assets", name="assets")

        @app.get("/<path:path>")
        async def spa(_request: Request, path: str):
            requested = frontend / path
            if requested.is_file() and frontend in requested.resolve().parents:
                return await file(requested)
            return await file(frontend / "index.html")

        @app.get("/")
        async def spa_root(_request: Request):
            return await file(frontend / "index.html")

    @app.after_server_stop
    async def close_database(_app: Sanic):
        await _app.ctx.db.close()

    return app


app = create_app()
