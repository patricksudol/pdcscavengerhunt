from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select

from pdcscavengerhunt.cloudflare_media import StreamVideo
from pdcscavengerhunt.models import (
    AuditEvent,
    Clue,
    ClueCompletion,
    ClueMedia,
    Game,
    GamePlayer,
    User,
)
from pdcscavengerhunt.security import fingerprint_code

from .conftest import auth

PHOTO_BYTES = b"\x89PNG\r\n\x1a\n" + b"photo-content"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"video-content"


@dataclass
class FakeMediaProvider:
    photos: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    videos: dict[str, StreamVideo] = field(default_factory=dict)
    deleted_photos: list[str] = field(default_factory=list)
    deleted_videos: list[str] = field(default_factory=list)
    last_video_uid: str | None = None
    next_video_status: str = "ready"
    webhook_payload: dict = field(default_factory=dict)

    async def upload_photo(
        self,
        key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        self.photos[key] = (content, content_type)

    def create_photo_read_url(self, key: str) -> str:
        return f"https://r2.example/read/{key}?signed=true"

    async def delete_photo(self, key: str) -> None:
        self.photos.pop(key, None)
        self.deleted_photos.append(key)

    async def create_video_upload(
        self,
        *,
        clue_id: str,
        original_filename: str,
    ) -> tuple[str, str]:
        uid = f"stream-{len(self.videos) + 1}"
        self.last_video_uid = uid
        self.videos[uid] = StreamVideo(0, "processing", False)
        return uid, f"https://stream-upload.example/{uid}"

    async def upload_video(
        self,
        *,
        clue_id: str,
        original_filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        uid, _upload_url = await self.create_video_upload(
            clue_id=clue_id,
            original_filename=original_filename,
        )
        self.videos[uid] = StreamVideo(
            len(content),
            self.next_video_status,
            self.next_video_status == "ready",
        )
        return uid

    async def video_details(self, uid: str) -> StreamVideo:
        return self.videos[uid]

    async def secure_video(self, _uid: str) -> None:
        return None

    async def create_video_player_url(self, uid: str) -> str:
        return f"https://customer-test.cloudflarestream.com/token-{uid}/iframe"

    async def delete_video(self, uid: str) -> None:
        self.videos.pop(uid, None)
        self.deleted_videos.append(uid)

    def verify_stream_webhook(self, _body: bytes, _signature: str) -> bool:
        return True

    def parse_webhook(self, _body: bytes) -> dict:
        return self.webhook_payload


async def make_media_game(app):
    player = User(
        email_address="media-player@example.com",
        normalized_email_address="media-player@example.com",
        full_name="Media Player",
    )
    stranger = User(
        email_address="media-stranger@example.com",
        normalized_email_address="media-stranger@example.com",
        full_name="Media Stranger",
    )
    game = Game(title="Media Game", status="open")
    async with app.ctx.db.session() as db:
        db.add_all([player, stranger, game])
        await db.flush()
        membership = GamePlayer(game_id=game.id, user_id=player.id)
        clues = [
            Clue(
                game_id=game.id,
                position=position,
                title=f"Media Clue {position}",
                content=f"Media Answer {position}",
                code=f"MEDIA-{position}",
                code_fingerprint=fingerprint_code(
                    f"MEDIA-{position}", app.ctx.settings
                ),
            )
            for position in (1, 2)
        ]
        db.add_all([membership, *clues])
        await db.flush()
    return player, stranger, game, membership, clues


async def upload_media(
    app,
    admin,
    provider: FakeMediaProvider,
    clue,
    media_type: str,
    content: bytes,
    content_type: str,
    filename: str,
    *,
    video_status: str = "ready",
):
    cookies, headers = auth(app, admin)
    path = f"/api/v1/admin/clues/{clue.id}/media/{media_type}"
    provider.next_video_status = video_status
    return await app.asgi_client.put(
        path,
        content=content,
        cookies=cookies,
        headers={
            **headers,
            "Content-Type": content_type,
            "X-File-Name": filename,
        },
    )


async def test_admin_uploads_cloudflare_media_and_player_gets_private_redirects(
    app,
    admin,
):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    player, _stranger, game, _membership, clues = await make_media_game(app)
    _request, photo = await upload_media(
        app, admin, provider, clues[0], "photo", PHOTO_BYTES, "image/png", "map.png"
    )
    _request, video = await upload_media(
        app,
        admin,
        provider,
        clues[0],
        "video",
        VIDEO_BYTES,
        "video/quicktime",
        "welcome.mov",
    )
    assert photo.status == 201
    assert video.status == 201
    assert photo.json["status"] == "ready"
    assert video.json["status"] == "ready"
    assert video.json["content_type"] == "video/quicktime"

    player_cookies, _headers = auth(app, player)
    _request, state = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=player_cookies,
    )
    current = state.json["clues"][0]
    assert current["photo"]["url"] == photo.json["url"]
    assert current["video"]["url"] == video.json["url"]

    _request, image_response = await app.asgi_client.get(
        photo.json["url"],
        cookies=player_cookies,
    )
    assert image_response.status == 302
    assert image_response.headers["location"].startswith("https://r2.example/read/")

    _request, video_response = await app.asgi_client.get(
        video.json["url"],
        cookies=player_cookies,
    )
    assert video_response.status == 302
    assert "cloudflarestream.com" in video_response.headers["location"]
    assert video_response.headers["x-frame-options"] == "SAMEORIGIN"

    async with app.ctx.db.session() as db:
        assert await db.scalar(select(func.count(ClueMedia.id))) == 2
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert "clue.media_attached" in actions


async def test_media_is_hidden_until_player_reaches_clue(app, admin):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    player, stranger, _game, membership, clues = await make_media_game(app)
    _request, uploaded = await upload_media(
        app, admin, provider, clues[1], "photo", PHOTO_BYTES, "image/png", "future.png"
    )

    player_cookies, _headers = auth(app, player)
    _request, unavailable = await app.asgi_client.get(
        uploaded.json["url"],
        cookies=player_cookies,
    )
    assert unavailable.status == 404
    stranger_cookies, _headers = auth(app, stranger)
    _request, unassigned = await app.asgi_client.get(
        uploaded.json["url"],
        cookies=stranger_cookies,
    )
    assert unassigned.status == 404

    async with app.ctx.db.session() as db:
        db.add(ClueCompletion(game_player_id=membership.id, clue_id=clues[0].id))
    _request, available = await app.asgi_client.get(
        uploaded.json["url"],
        cookies=player_cookies,
    )
    assert available.status == 302


async def test_replacing_removing_and_deleting_media_cleans_up_cloudflare(
    app,
    admin,
):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    _player, _stranger, _game, _membership, clues = await make_media_game(app)
    _request, first = await upload_media(
        app, admin, provider, clues[0], "photo", PHOTO_BYTES, "image/png", "first.png"
    )
    async with app.ctx.db.session() as db:
        first_row = await db.scalar(
            select(ClueMedia).where(ClueMedia.id == UUID(first.json["id"]))
        )
        first_key = first_row.provider_key

    replacement = b"\x89PNG\r\n\x1a\nreplacement"
    _request, second = await upload_media(
        app, admin, provider, clues[0], "photo", replacement, "image/png", "second.png"
    )
    assert second.status == 200
    assert second.json["id"] == first.json["id"]
    assert first_key in provider.deleted_photos

    cookies, headers = auth(app, admin)
    _request, removed = await app.asgi_client.delete(
        f"/api/v1/admin/clues/{clues[0].id}/media/photo",
        cookies=cookies,
        headers=headers,
    )
    assert removed.status == 200
    async with app.ctx.db.session() as db:
        assert await db.scalar(select(ClueMedia.id)) is None

    _request, video = await upload_media(
        app, admin, provider, clues[1], "video", VIDEO_BYTES, "video/mp4", "delete.mp4"
    )
    _request, deleted = await app.asgi_client.delete(
        f"/api/v1/admin/clues/{clues[1].id}",
        cookies=cookies,
        headers=headers,
    )
    assert deleted.status == 200
    assert provider.deleted_videos
    async with app.ctx.db.session() as db:
        assert await db.scalar(
            select(ClueMedia.id).where(ClueMedia.id == UUID(video.json["id"]))
        ) is None


async def test_upload_rejects_invalid_type_signature_and_size(app, admin):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    _player, _stranger, _game, _membership, clues = await make_media_game(app)
    cookies, headers = auth(app, admin)
    path = f"/api/v1/admin/clues/{clues[0].id}/media/photo"

    _request, bad_type = await app.asgi_client.put(
        path,
        content=b"<svg>",
        cookies=cookies,
        headers={
            **headers,
            "Content-Type": "image/svg+xml",
            "X-File-Name": "unsafe.svg",
        },
    )
    assert bad_type.status == 400

    app.ctx.settings.photo_max_bytes = len(PHOTO_BYTES) - 1
    _request, too_large = await app.asgi_client.put(
        path,
        content=PHOTO_BYTES,
        cookies=cookies,
        headers={
            **headers,
            "Content-Type": "image/png",
            "X-File-Name": "large.png",
        },
    )
    assert too_large.status == 413
    app.ctx.settings.photo_max_bytes = 8 * 1024 * 1024

    _request, invalid = await upload_media(
        app,
        admin,
        provider,
        clues[0],
        "photo",
        b"not-a-png",
        "image/png",
        "fake.png",
    )
    assert invalid.status == 400
    async with app.ctx.db.session() as db:
        assert await db.scalar(select(ClueMedia.id)) is None


async def test_processing_video_is_not_exposed_to_player(app, admin):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    player, _stranger, game, _membership, clues = await make_media_game(app)
    _request, uploaded = await upload_media(
        app,
        admin,
        provider,
        clues[0],
        "video",
        VIDEO_BYTES,
        "video/mp4",
        "processing.mp4",
        video_status="processing",
    )
    assert uploaded.json["status"] == "processing"

    player_cookies, _headers = auth(app, player)
    _request, state = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=player_cookies,
    )
    assert state.json["clues"][0]["video"] is None

    provider.webhook_payload = {
        "uid": provider.last_video_uid,
        "readyToStream": True,
        "size": len(VIDEO_BYTES),
        "status": {"state": "ready"},
    }
    _request, webhook = await app.asgi_client.post(
        "/api/v1/media/cloudflare-stream/webhook",
        content=b"webhook",
        headers={"Webhook-Signature": "test"},
    )
    assert webhook.status == 200

    _request, refreshed = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=player_cookies,
    )
    assert refreshed.json["clues"][0]["video"]["status"] == "ready"
    async with app.ctx.db.session() as db:
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert "clue.media_ready" in actions


async def test_missed_webhook_is_reconciled_when_game_is_reloaded(app, admin):
    provider = FakeMediaProvider()
    app.ctx.media = provider
    player, _stranger, game, _membership, clues = await make_media_game(app)
    _request, uploaded = await upload_media(
        app,
        admin,
        provider,
        clues[0],
        "video",
        VIDEO_BYTES,
        "video/quicktime",
        "reconcile.mov",
        video_status="processing",
    )
    assert uploaded.json["status"] == "processing"
    assert provider.last_video_uid
    provider.videos[provider.last_video_uid] = StreamVideo(
        len(VIDEO_BYTES),
        "ready",
        True,
    )

    player_cookies, _headers = auth(app, player)
    _request, refreshed = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=player_cookies,
    )
    assert refreshed.status == 200
    assert refreshed.json["clues"][0]["video"]["status"] == "ready"

    async with app.ctx.db.session() as db:
        media = await db.get(ClueMedia, UUID(uploaded.json["id"]))
        assert media.status == "ready"
        event = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "clue.media_ready")
        )
        assert event.reason == "Reconciled with Cloudflare Stream"
