from __future__ import annotations

from sanic import Request
from sanic.log import logger

from .cloudflare_media import MediaProviderError
from .models import AuditEvent, ClueMedia, MediaType


async def refresh_processing_videos(
    request: Request,
    db,
    media_items: list[ClueMedia],
) -> None:
    for media in media_items:
        if media.media_type != MediaType.video or media.status != "processing":
            continue
        try:
            video = await request.app.ctx.media.video_details(media.provider_key)
        except MediaProviderError:
            logger.exception(
                "Unable to refresh Stream video status for %s",
                media.provider_key,
            )
            continue
        if video.size_bytes:
            media.size_bytes = video.size_bytes
        if video.status == media.status:
            continue
        previous_status = media.status
        media.status = video.status
        db.add(
            AuditEvent(
                action=f"clue.media_{video.status}",
                entity_type="clue",
                entity_id=str(media.clue_id),
                before={"status": previous_status},
                after={"status": video.status, "media_id": str(media.id)},
                reason="Reconciled with Cloudflare Stream",
                request_id=request.ctx.request_id,
            )
        )
