from __future__ import annotations

from uuid import UUID

from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, NotFound, ServiceUnavailable, Unauthorized
from sanic.log import logger
from sanic.response import redirect
from sqlalchemy import func, select

from .cloudflare_media import MediaProviderError
from .models import (
    AuditEvent,
    Clue,
    ClueCompletion,
    ClueMedia,
    Game,
    GamePlayer,
    GameStatus,
    MediaType,
)
from .security import login_required

media_bp = Blueprint("media", url_prefix="/api/v1/media")


async def player_can_access(db, request: Request, clue: Clue, game: Game) -> bool:
    if request.ctx.user.is_admin:
        return True
    if game.status == GameStatus.draft:
        return False
    membership = await db.scalar(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id,
            GamePlayer.user_id == request.ctx.user.id,
        )
    )
    if not membership:
        return False
    earlier_count = (
        await db.scalar(
            select(func.count(Clue.id)).where(
                Clue.game_id == game.id,
                Clue.position < clue.position,
            )
        )
        or 0
    )
    completed_earlier_count = (
        await db.scalar(
            select(func.count(ClueCompletion.id))
            .join(Clue, Clue.id == ClueCompletion.clue_id)
            .where(
                ClueCompletion.game_player_id == membership.id,
                Clue.game_id == game.id,
                Clue.position < clue.position,
            )
        )
        or 0
    )
    return completed_earlier_count == earlier_count


@media_bp.get("/<media_id:uuid>")
@login_required()
async def serve_media(request: Request, media_id: UUID):
    async with request.app.ctx.db.session() as db:
        row = (
            await db.execute(
                select(ClueMedia, Clue, Game)
                .join(Clue, Clue.id == ClueMedia.clue_id)
                .join(Game, Game.id == Clue.game_id)
                .where(ClueMedia.id == media_id)
            )
        ).one_or_none()
        if not row:
            raise NotFound("Media not found")
        media, clue, game = row
        if not await player_can_access(db, request, clue, game):
            raise NotFound("Media not found")
        if media.status != "ready":
            raise ServiceUnavailable("This media is still processing")

    try:
        destination = (
            request.app.ctx.media.create_photo_read_url(media.provider_key)
            if media.media_type == MediaType.photo
            else await request.app.ctx.media.create_video_player_url(media.provider_key)
        )
    except MediaProviderError as error:
        logger.exception(
            "event=media_playback_authorization_failed request_id=%s "
            "media_id=%s media_type=%s",
            request.ctx.request_id,
            media.id,
            media.media_type.value,
        )
        raise ServiceUnavailable(str(error)) from error
    logger.info(
        "event=media_playback_authorized request_id=%s media_id=%s "
        "media_type=%s user_id=%s",
        request.ctx.request_id,
        media.id,
        media.media_type.value,
        request.ctx.user.id,
    )
    return redirect(destination, status=302)


@media_bp.post("/cloudflare-stream/webhook")
async def stream_webhook(request: Request):
    signature = request.headers.get("webhook-signature", "")
    if not request.app.ctx.media.verify_stream_webhook(request.body, signature):
        logger.warning(
            "event=stream_webhook_rejected request_id=%s reason=invalid_signature",
            request.ctx.request_id,
        )
        raise Unauthorized("Invalid Stream webhook signature")
    try:
        payload = request.app.ctx.media.parse_webhook(request.body)
        uid = str(payload["uid"])
    except (KeyError, MediaProviderError) as error:
        logger.warning(
            "event=stream_webhook_rejected request_id=%s reason=invalid_payload",
            request.ctx.request_id,
        )
        raise InvalidUsage("Invalid Stream webhook payload") from error

    ready = bool(payload.get("readyToStream"))
    provider_state = str((payload.get("status") or {}).get("state", "processing"))
    status = "ready" if ready else "error" if provider_state == "error" else "processing"
    size_bytes = int(payload.get("size") or 0)
    delete_oversized = False
    async with request.app.ctx.db.session() as db:
        media = await db.scalar(
            select(ClueMedia).where(
                ClueMedia.provider_key == uid,
                ClueMedia.media_type == MediaType.video,
            )
        )
        if not media:
            logger.warning(
                "event=stream_webhook_unmatched request_id=%s stream_uid=%s "
                "provider_status=%s",
                request.ctx.request_id,
                uid,
                status,
            )
            return {"received": True}
        previous_status = media.status
        if previous_status == "ready" and status == "processing":
            status = "ready"
        if size_bytes:
            media.size_bytes = size_bytes
        if size_bytes > request.app.ctx.settings.video_max_bytes:
            status = "error"
            delete_oversized = True
        media.status = status
        if previous_status != status:
            db.add(
                AuditEvent(
                    action=f"clue.media_{status}",
                    entity_type="clue",
                    entity_id=str(media.clue_id),
                    before={"status": previous_status},
                    after={"status": status, "media_id": str(media.id)},
                    reason=(
                        "Video exceeded the configured size limit"
                        if delete_oversized
                        else None
                    ),
                    request_id=request.ctx.request_id,
                )
            )
        logger.info(
            "event=stream_webhook_processed request_id=%s stream_uid=%s "
            "media_id=%s previous_status=%s provider_status=%s size_bytes=%s "
            "status_changed=%s",
            request.ctx.request_id,
            uid,
            media.id,
            previous_status,
            status,
            size_bytes,
            previous_status != status,
        )
    if delete_oversized:
        try:
            await request.app.ctx.media.delete_video(uid)
        except MediaProviderError:
            logger.exception("Unable to delete oversized Stream video %s", uid)
    return {"received": True}
