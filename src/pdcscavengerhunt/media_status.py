from __future__ import annotations

from sanic import Request
from sanic.log import logger

from .cloudflare_media import MediaProviderError
from .models import AuditEvent, ClueMedia, HintMedia, MediaType


async def refresh_processing_videos(
    request: Request,
    db,
    media_items: list[ClueMedia] | list[HintMedia],
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
        logger.info(
            "event=stream_status_reconciled request_id=%s stream_uid=%s "
            "media_id=%s previous_status=%s provider_status=%s size_bytes=%s",
            request.ctx.request_id,
            media.provider_key,
            media.id,
            previous_status,
            video.status,
            media.size_bytes,
        )
        db.add(
            AuditEvent(
                action=(
                    f"clue.media_{video.status}"
                    if isinstance(media, ClueMedia)
                    else f"hint.media_{video.status}"
                ),
                entity_type="clue" if isinstance(media, ClueMedia) else "hint",
                entity_id=str(
                    media.clue_id
                    if isinstance(media, ClueMedia)
                    else media.hint_id
                ),
                before={"status": previous_status},
                after={"status": video.status, "media_id": str(media.id)},
                reason="Reconciled with Cloudflare Stream",
                request_id=request.ctx.request_id,
            )
        )
