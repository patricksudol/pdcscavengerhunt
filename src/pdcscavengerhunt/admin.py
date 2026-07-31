from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote
from uuid import UUID, uuid4

from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, NotFound, SanicException
from sanic.log import logger
from sqlalchemy import and_, delete, func, or_, select, update

from .auth import setup_token_hash
from .cloudflare_media import MediaProviderError
from .media_status import refresh_processing_videos
from .models import (
    AuditEvent,
    Clue,
    ClueAnswerReveal,
    ClueCompletion,
    ClueMedia,
    Game,
    GamePlayer,
    Hint,
    HintMedia,
    HintReveal,
    MediaType,
    PasswordSetupToken,
    User,
)
from .schemas import (
    ClueCreate,
    ClueReorder,
    ClueUpdate,
    GameCreate,
    GameUpdate,
    HintCreate,
    HintReorder,
    HintUpdate,
    MembershipUpdate,
    ProgressAdvance,
    ProgressReset,
    UserCreate,
    UserUpdate,
)
from .security import (
    fingerprint_code,
    login_required,
    normalize_code,
    normalize_email_address,
)

admin_bp = Blueprint("admin", url_prefix="/api/v1/admin")

MEDIA_CONTENT_TYPES = {
    MediaType.photo: {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    },
    MediaType.video: {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
    },
}

GAME_AUDIT_ENTITY_TYPES = ("game", "clue", "hint", "game_player")


def general_audit_filter():
    """Limit the Players audit trail to activity outside a specific game."""
    return and_(
        AuditEvent.entity_type.not_in(GAME_AUDIT_ENTITY_TYPES),
        func.coalesce(AuditEvent.after["game_id"].as_string(), "") == "",
        func.coalesce(AuditEvent.before["game_id"].as_string(), "") == "",
        func.coalesce(AuditEvent.after["clue_id"].as_string(), "") == "",
        func.coalesce(AuditEvent.before["clue_id"].as_string(), "") == "",
    )


def audit(
    request: Request,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        actor_id=request.ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
        request_id=request.ctx.request_id,
    )


def user_json(user: User, *, game_count: int | None = None) -> dict:
    result = {
        "id": str(user.id),
        "email_address": user.email_address,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "active": user.active,
        "password_set": user.password_hash is not None,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }
    if game_count is not None:
        result["game_count"] = game_count
    return result


def audit_user_json(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": str(user.id),
        "email_address": user.email_address,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
    }


def audit_subject_id(event: AuditEvent) -> UUID | None:
    candidate = (
        event.entity_id
        if event.entity_type == "user"
        else event.after.get("user_id")
        if event.after
        else None
    )
    try:
        return UUID(candidate) if isinstance(candidate, str) else None
    except ValueError:
        return None


def audit_uuid(value: object) -> UUID | None:
    try:
        return UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None


def audit_game_id(event: AuditEvent) -> UUID | None:
    if event.entity_type == "game":
        return audit_uuid(event.entity_id)
    for snapshot in (event.after, event.before):
        if snapshot and (game_id := audit_uuid(snapshot.get("game_id"))):
            return game_id
    return None


def audit_clue_id(event: AuditEvent) -> UUID | None:
    if event.entity_type == "clue":
        return audit_uuid(event.entity_id)
    for snapshot in (event.after, event.before):
        if snapshot and (clue_id := audit_uuid(snapshot.get("clue_id"))):
            return clue_id
    return None


def audit_hint_id(event: AuditEvent) -> UUID | None:
    return audit_uuid(event.entity_id) if event.entity_type == "hint" else None


def media_json(media: ClueMedia | HintMedia) -> dict:
    return {
        "id": str(media.id),
        "media_type": media.media_type.value,
        "original_filename": media.original_filename,
        "content_type": media.content_type,
        "size_bytes": media.size_bytes,
        "status": media.status,
        "url": f"/api/v1/media/{media.id}",
        "created_at": media.created_at.isoformat(),
    }


def hint_json(hint: Hint, media: list[HintMedia] | None = None) -> dict:
    by_type = {item.media_type: item for item in media or []}
    return {
        "id": str(hint.id),
        "position": hint.position,
        "text": hint.text,
        "photo": (media_json(by_type[MediaType.photo]) if MediaType.photo in by_type else None),
        "video": (media_json(by_type[MediaType.video]) if MediaType.video in by_type else None),
    }


def clue_json(
    clue: Clue,
    media: list[ClueMedia] | None = None,
    hints: list[dict] | None = None,
) -> dict:
    by_type = {item.media_type: item for item in media or []}
    return {
        "id": str(clue.id),
        "position": clue.position,
        "title": clue.title,
        "content": clue.content,
        "code": clue.code,
        "code_set": True,
        "photo": (media_json(by_type[MediaType.photo]) if MediaType.photo in by_type else None),
        "video": (media_json(by_type[MediaType.video]) if MediaType.video in by_type else None),
        "hints": hints or [],
    }


def media_audit_json(media: ClueMedia | HintMedia) -> dict:
    return {
        "id": str(media.id),
        "media_type": media.media_type.value,
        "original_filename": media.original_filename,
        "content_type": media.content_type,
        "size_bytes": media.size_bytes,
        "status": media.status,
    }


def valid_media_signature(media_type: MediaType, content_type: str, prefix: bytes) -> bool:
    if media_type == MediaType.video:
        return (
            content_type in MEDIA_CONTENT_TYPES[MediaType.video]
            and len(prefix) >= 12
            and prefix[4:8] == b"ftyp"
        )
    if content_type == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"
    return False


async def delete_provider_media(
    request: Request,
    media_type: MediaType,
    provider_key: str | None,
) -> None:
    if not provider_key:
        return
    try:
        if media_type == MediaType.photo:
            await request.app.ctx.media.delete_photo(provider_key)
        else:
            await request.app.ctx.media.delete_video(provider_key)
    except MediaProviderError:
        logger.exception("Unable to delete clue media %s", provider_key)


def game_json(
    game: Game,
    *,
    player_count: int = 0,
    clue_count: int = 0,
    completion_count: int = 0,
) -> dict:
    return {
        "id": str(game.id),
        "title": game.title,
        "description": game.description,
        "instructions": game.instructions,
        "closing_message": game.closing_message,
        "allow_answer_reveal": game.allow_answer_reveal,
        "status": game.status.value,
        "player_count": player_count,
        "clue_count": clue_count,
        "completion_count": completion_count,
        "created_at": game.created_at.isoformat(),
        "updated_at": game.updated_at.isoformat(),
    }


async def create_setup_link(db, request: Request, user: User) -> str:
    now = datetime.now(UTC)
    await db.execute(
        update(PasswordSetupToken)
        .where(
            PasswordSetupToken.user_id == user.id,
            PasswordSetupToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordSetupToken(
            user_id=user.id,
            token_hash=setup_token_hash(raw_token),
            created_by_id=request.ctx.user.id,
            expires_at=now + timedelta(hours=24),
        )
    )
    return f"{request.app.ctx.settings.public_base_url}/setup-password/{raw_token}"


@admin_bp.get("/dashboard")
@login_required(admin=True)
async def dashboard(request: Request):
    async with request.app.ctx.db.session() as db:
        users = await db.scalar(select(func.count(User.id)).where(User.active.is_(True)))
        games = await db.scalar(select(func.count(Game.id)))
        open_games = await db.scalar(select(func.count(Game.id)).where(Game.status == "open"))
        completions = await db.scalar(select(func.count(ClueCompletion.id)))
        return {
            "users": users or 0,
            "games": games or 0,
            "open_games": open_games or 0,
            "completions": completions or 0,
        }


@admin_bp.get("/users")
@login_required(admin=True)
async def list_users(request: Request):
    async with request.app.ctx.db.session() as db:
        rows = (
            await db.execute(
                select(User, func.count(GamePlayer.id))
                .outerjoin(GamePlayer, GamePlayer.user_id == User.id)
                .group_by(User.id)
                .order_by(User.full_name, User.email_address)
            )
        ).all()
        return [user_json(user, game_count=count) for user, count in rows]


@admin_bp.get("/audit-events")
@login_required(admin=True)
async def list_audit_events(request: Request):
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise InvalidUsage("Audit pagination values must be integers") from error
    if not 1 <= limit <= 100:
        raise InvalidUsage("Audit limit must be between 1 and 100")
    if offset < 0:
        raise InvalidUsage("Audit offset cannot be negative")
    game_id = None
    if supplied_game_id := request.args.get("game_id"):
        try:
            game_id = UUID(supplied_game_id)
        except ValueError as error:
            raise InvalidUsage("Audit game ID must be a UUID") from error

    async with request.app.ctx.db.session() as db:
        game_filter = None
        if game_id:
            clue_ids = [
                str(clue_id)
                for clue_id in (
                    await db.scalars(select(Clue.id).where(Clue.game_id == game_id))
                ).all()
            ]
            hint_ids = [
                str(hint_id)
                for hint_id in (
                    await db.scalars(
                        select(Hint.id)
                        .join(Clue, Clue.id == Hint.clue_id)
                        .where(Clue.game_id == game_id)
                    )
                ).all()
            ]
            membership_ids = [
                str(membership_id)
                for membership_id in (
                    await db.scalars(select(GamePlayer.id).where(GamePlayer.game_id == game_id))
                ).all()
            ]
            game_id_text = str(game_id)
            game_filter = or_(
                (AuditEvent.entity_type == "game") & (AuditEvent.entity_id == game_id_text),
                (AuditEvent.entity_type == "game_player")
                & AuditEvent.entity_id.in_(membership_ids),
                AuditEvent.after["game_id"].as_string() == game_id_text,
                AuditEvent.before["game_id"].as_string() == game_id_text,
                (AuditEvent.entity_type == "clue") & AuditEvent.entity_id.in_(clue_ids),
                (AuditEvent.entity_type == "hint") & AuditEvent.entity_id.in_(hint_ids),
                AuditEvent.after["clue_id"].as_string().in_(clue_ids),
                AuditEvent.before["clue_id"].as_string().in_(clue_ids),
            )

        audit_filter = game_filter if game_filter is not None else general_audit_filter()
        count_query = select(func.count(AuditEvent.id)).where(audit_filter)
        total = await db.scalar(count_query) or 0
        events_query = (
            select(AuditEvent, User)
            .outerjoin(User, User.id == AuditEvent.actor_id)
            .where(audit_filter)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(events_query)).all()
        subject_ids = {
            subject_id for event, _actor in rows if (subject_id := audit_subject_id(event))
        }
        subjects = (
            {
                user.id: user
                for user in (await db.scalars(select(User).where(User.id.in_(subject_ids)))).all()
            }
            if subject_ids
            else {}
        )
        clue_ids = {clue_id for event, _actor in rows if (clue_id := audit_clue_id(event))}
        clue_game_ids = (
            dict(
                (await db.execute(select(Clue.id, Clue.game_id).where(Clue.id.in_(clue_ids)))).all()
            )
            if clue_ids
            else {}
        )
        hint_ids = {hint_id for event, _actor in rows if (hint_id := audit_hint_id(event))}
        hint_game_ids = (
            dict(
                (
                    await db.execute(
                        select(Hint.id, Clue.game_id)
                        .join(Clue, Clue.id == Hint.clue_id)
                        .where(Hint.id.in_(hint_ids))
                    )
                ).all()
            )
            if hint_ids
            else {}
        )
        game_ids = {
            game_id
            for event, _actor in rows
            if (
                game_id := audit_game_id(event)
                or clue_game_ids.get(audit_clue_id(event))
                or hint_game_ids.get(audit_hint_id(event))
            )
        }
        games = (
            {
                game.id: game
                for game in (await db.scalars(select(Game).where(Game.id.in_(game_ids)))).all()
            }
            if game_ids
            else {}
        )

        def event_game(event: AuditEvent) -> Game | None:
            game_id = (
                audit_game_id(event)
                or clue_game_ids.get(audit_clue_id(event))
                or hint_game_ids.get(audit_hint_id(event))
            )
            return games.get(game_id)

        return {
            "items": [
                {
                    "id": str(event.id),
                    "action": event.action,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "reason": event.reason,
                    "before": event.before,
                    "after": event.after,
                    "request_id": event.request_id,
                    "created_at": event.created_at.isoformat(),
                    "actor": audit_user_json(actor),
                    "subject": audit_user_json(subjects.get(audit_subject_id(event))),
                    "game": (
                        {"id": str(game.id), "title": game.title}
                        if (game := event_game(event))
                        else None
                    ),
                }
                for event, actor in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@admin_bp.post("/users")
@login_required(admin=True)
async def create_user(request: Request):
    payload = UserCreate.model_validate(request.json or {})
    normalized = normalize_email_address(str(payload.email_address))
    async with request.app.ctx.db.session() as db:
        if await db.scalar(select(User.id).where(User.normalized_email_address == normalized)):
            raise SanicException("That email address is already in use", status_code=409)
        user = User(
            email_address=str(payload.email_address).strip(),
            normalized_email_address=normalized,
            full_name=payload.full_name.strip(),
            is_admin=payload.is_admin,
        )
        db.add(user)
        await db.flush()
        setup_url = await create_setup_link(db, request, user)
        db.add(
            audit(
                request,
                action="user.created",
                entity_type="user",
                entity_id=str(user.id),
                after=user_json(user),
            )
        )
        return {**user_json(user), "setup_url": setup_url}, 201


@admin_bp.patch("/users/<user_id:uuid>")
@login_required(admin=True)
async def update_user(request: Request, user_id: UUID):
    payload = UserUpdate.model_validate(request.json or {})
    changes = payload.model_dump(exclude_unset=True)
    async with request.app.ctx.db.session() as db:
        user = await db.get(User, user_id)
        if not user:
            raise NotFound("User not found")
        if user.id == request.ctx.user.id and (
            changes.get("active") is False or changes.get("is_admin") is False
        ):
            raise InvalidUsage("You cannot remove your own administrator access")
        if (
            user.is_admin
            and user.active
            and (changes.get("active") is False or changes.get("is_admin") is False)
        ):
            admin_count = await db.scalar(
                select(func.count(User.id)).where(User.is_admin.is_(True), User.active.is_(True))
            )
            if (admin_count or 0) <= 1:
                raise InvalidUsage("At least one active administrator is required")
        before = user_json(user)
        if email_address := changes.pop("email_address", None):
            normalized = normalize_email_address(str(email_address))
            duplicate = await db.scalar(
                select(User.id).where(
                    User.normalized_email_address == normalized,
                    User.id != user.id,
                )
            )
            if duplicate:
                raise SanicException(
                    "That email address is already in use",
                    status_code=409,
                )
            user.email_address = str(email_address).strip()
            user.normalized_email_address = normalized
        for key, value in changes.items():
            if key == "full_name" and value is not None:
                value = value.strip()
            setattr(user, key, value)
        if email_address or "active" in changes or "is_admin" in changes:
            user.session_version += 1
        await db.flush()
        after = user_json(user)
        db.add(
            audit(
                request,
                action="user.updated",
                entity_type="user",
                entity_id=str(user.id),
                before=before,
                after=after,
            )
        )
        return after


@admin_bp.delete("/users/<user_id:uuid>")
@login_required(admin=True)
async def delete_user(request: Request, user_id: UUID):
    async with request.app.ctx.db.session() as db:
        user = await db.get(User, user_id)
        if not user:
            raise NotFound("User not found")
        if user.id == request.ctx.user.id:
            raise InvalidUsage("You cannot delete your own account")

        before = user_json(user)
        db.add(
            audit(
                request,
                action="user.deleted",
                entity_type="user",
                entity_id=str(user.id),
                before=before,
            )
        )

        # Keep historical records, but remove the account's credentials,
        # assignments, and progress. These statements also make deletion
        # consistent in SQLite environments where FK cascades may be disabled.
        await db.execute(
            update(PasswordSetupToken)
            .where(PasswordSetupToken.created_by_id == user.id)
            .values(created_by_id=None)
        )
        await db.execute(delete(PasswordSetupToken).where(PasswordSetupToken.user_id == user.id))
        membership_ids = select(GamePlayer.id).where(GamePlayer.user_id == user.id)
        await db.execute(
            delete(ClueCompletion).where(ClueCompletion.game_player_id.in_(membership_ids))
        )
        await db.execute(delete(GamePlayer).where(GamePlayer.user_id == user.id))
        await db.execute(
            update(GamePlayer)
            .where(GamePlayer.assigned_by_id == user.id)
            .values(assigned_by_id=None)
        )
        await db.execute(
            update(Game).where(Game.created_by_id == user.id).values(created_by_id=None)
        )
        await db.execute(
            update(ClueMedia).where(ClueMedia.created_by_id == user.id).values(created_by_id=None)
        )
        await db.execute(
            update(AuditEvent).where(AuditEvent.actor_id == user.id).values(actor_id=None)
        )
        await db.execute(delete(User).where(User.id == user.id))
        return {"deleted": True}


@admin_bp.post("/users/<user_id:uuid>/setup-link")
@login_required(admin=True)
async def regenerate_setup_link(request: Request, user_id: UUID):
    async with request.app.ctx.db.session() as db:
        user = await db.get(User, user_id)
        if not user or not user.active:
            raise NotFound("Active user not found")
        setup_url = await create_setup_link(db, request, user)
        db.add(
            audit(
                request,
                action="user.setup_link_generated",
                entity_type="user",
                entity_id=str(user.id),
            )
        )
        return {"setup_url": setup_url}


@admin_bp.get("/games")
@login_required(admin=True)
async def list_games(request: Request):
    async with request.app.ctx.db.session() as db:
        games = list((await db.scalars(select(Game).order_by(Game.created_at.desc()))).all())
        result = []
        for game in games:
            player_count = await db.scalar(
                select(func.count(GamePlayer.id)).where(GamePlayer.game_id == game.id)
            )
            clue_count = await db.scalar(select(func.count(Clue.id)).where(Clue.game_id == game.id))
            completion_count = await db.scalar(
                select(func.count(ClueCompletion.id))
                .join(Clue, Clue.id == ClueCompletion.clue_id)
                .where(Clue.game_id == game.id)
            )
            result.append(
                game_json(
                    game,
                    player_count=player_count or 0,
                    clue_count=clue_count or 0,
                    completion_count=completion_count or 0,
                )
            )
        return result


@admin_bp.post("/games")
@login_required(admin=True)
async def create_game(request: Request):
    payload = GameCreate.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        game = Game(
            title=payload.title.strip(),
            description=payload.description,
            instructions=payload.instructions,
            closing_message=payload.closing_message,
            allow_answer_reveal=payload.allow_answer_reveal,
            created_by_id=request.ctx.user.id,
        )
        db.add(game)
        await db.flush()
        db.add(
            audit(
                request,
                action="game.created",
                entity_type="game",
                entity_id=str(game.id),
                after=game_json(game),
            )
        )
        return game_json(game), 201


@admin_bp.get("/games/<game_id:uuid>")
@login_required(admin=True)
async def get_game(request: Request, game_id: UUID):
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        if not game:
            raise NotFound("Game not found")
        clues = list(
            (
                await db.scalars(
                    select(Clue).where(Clue.game_id == game.id).order_by(Clue.position)
                )
            ).all()
        )
        clue_media = list(
            (
                await db.scalars(
                    select(ClueMedia).where(ClueMedia.clue_id.in_([clue.id for clue in clues]))
                )
            ).all()
        )
        await refresh_processing_videos(request, db, clue_media)
        media_by_clue: dict[UUID, list[ClueMedia]] = {}
        for media in clue_media:
            media_by_clue.setdefault(media.clue_id, []).append(media)
        hints = list(
            (
                await db.scalars(
                    select(Hint)
                    .where(Hint.clue_id.in_([clue.id for clue in clues]))
                    .order_by(Hint.clue_id, Hint.position)
                )
            ).all()
        )
        hint_media = list(
            (
                await db.scalars(
                    select(HintMedia).where(HintMedia.hint_id.in_([hint.id for hint in hints]))
                )
            ).all()
        )
        await refresh_processing_videos(request, db, hint_media)
        media_by_hint: dict[UUID, list[HintMedia]] = {}
        for media in hint_media:
            media_by_hint.setdefault(media.hint_id, []).append(media)
        hints_by_clue: dict[UUID, list[dict]] = {}
        for hint in hints:
            hints_by_clue.setdefault(hint.clue_id, []).append(
                hint_json(hint, media_by_hint.get(hint.id))
            )
        members = list(
            (
                await db.execute(
                    select(GamePlayer, User)
                    .join(User, User.id == GamePlayer.user_id)
                    .where(GamePlayer.game_id == game.id)
                    .order_by(User.full_name)
                )
            ).all()
        )
        progress = []
        for membership, user in members:
            completion_rows = (
                await db.execute(
                    select(
                        ClueCompletion.clue_id,
                        ClueCompletion.completed_at,
                    )
                    .where(ClueCompletion.game_player_id == membership.id)
                    .order_by(ClueCompletion.completed_at)
                )
            ).all()
            completions = [
                {
                    "clue_id": str(clue_id),
                    "completed_at": (
                        completed_at
                        if completed_at.tzinfo is not None
                        else completed_at.replace(tzinfo=UTC)
                    ).isoformat(),
                }
                for clue_id, completed_at in completion_rows
            ]
            completed_clue_ids = [completion["clue_id"] for completion in completions]
            finished_at = (
                completions[-1]["completed_at"]
                if clues and len(completions) == len(clues)
                else None
            )
            progress.append(
                {
                    "membership_id": str(membership.id),
                    "user": user_json(user),
                    "completed_count": len(completions),
                    "completed_clue_ids": completed_clue_ids,
                    "completions": completions,
                    "finished_at": finished_at,
                    "completion_rank": None,
                }
            )
        finishers = sorted(
            (item for item in progress if item["finished_at"] is not None),
            key=lambda item: (
                item["finished_at"],
                item["user"]["full_name"].casefold(),
                item["membership_id"],
            ),
        )
        for rank, item in enumerate(finishers, start=1):
            item["completion_rank"] = rank
        progress.sort(
            key=lambda item: (
                item["completion_rank"] is None,
                item["completion_rank"] or 0,
                item["user"]["full_name"].casefold(),
            )
        )
        return {
            **game_json(
                game,
                player_count=len(members),
                clue_count=len(clues),
                completion_count=sum(item["completed_count"] for item in progress),
            ),
            "clues": [
                clue_json(
                    clue,
                    media_by_clue.get(clue.id),
                    hints_by_clue.get(clue.id),
                )
                for clue in clues
            ],
            "players": progress,
        }


@admin_bp.patch("/games/<game_id:uuid>")
@login_required(admin=True)
async def update_game(request: Request, game_id: UUID):
    payload = GameUpdate.model_validate(request.json or {})
    changes = payload.model_dump(exclude_unset=True)
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        if not game:
            raise NotFound("Game not found")
        before = game_json(game)
        for key, value in changes.items():
            if key == "title" and value is not None:
                value = value.strip()
            setattr(game, key, value)
        await db.flush()
        after = game_json(game)
        db.add(
            audit(
                request,
                action="game.updated",
                entity_type="game",
                entity_id=str(game.id),
                before=before,
                after=after,
            )
        )
        return after


@admin_bp.put("/games/<game_id:uuid>/players")
@login_required(admin=True)
async def replace_players(request: Request, game_id: UUID):
    payload = MembershipUpdate.model_validate(request.json or {})
    try:
        user_ids = {UUID(value) for value in payload.user_ids}
    except ValueError as error:
        raise InvalidUsage("One or more user IDs are invalid") from error
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        if not game:
            raise NotFound("Game not found")
        valid_ids = set(
            (
                await db.scalars(
                    select(User.id).where(User.id.in_(user_ids), User.active.is_(True))
                )
            ).all()
        )
        if valid_ids != user_ids:
            raise InvalidUsage("Only active users can be assigned")
        memberships = list(
            (await db.scalars(select(GamePlayer).where(GamePlayer.game_id == game.id))).all()
        )
        existing = {membership.user_id: membership for membership in memberships}
        for removed_id in existing.keys() - user_ids:
            await db.delete(existing[removed_id])
        for added_id in user_ids - existing.keys():
            db.add(
                GamePlayer(
                    game_id=game.id,
                    user_id=added_id,
                    assigned_by_id=request.ctx.user.id,
                )
            )
        db.add(
            audit(
                request,
                action="game.players_updated",
                entity_type="game",
                entity_id=str(game.id),
                before={"user_ids": [str(value) for value in existing]},
                after={"user_ids": [str(value) for value in sorted(user_ids, key=str)]},
            )
        )
        return {"user_ids": [str(value) for value in sorted(user_ids, key=str)]}


async def code_available(db, fingerprint: str, *, excluding: UUID | None = None) -> bool:
    query = select(Clue.id).where(Clue.code_fingerprint == fingerprint)
    if excluding:
        query = query.where(Clue.id != excluding)
    return await db.scalar(query) is None


@admin_bp.post("/games/<game_id:uuid>/clues")
@login_required(admin=True)
async def create_clue(request: Request, game_id: UUID):
    payload = ClueCreate.model_validate(request.json or {})
    fingerprint = fingerprint_code(payload.code, request.app.ctx.settings)
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        if not game:
            raise NotFound("Game not found")
        if not await code_available(db, fingerprint):
            raise SanicException("That clue code is already in use", status_code=409)
        max_position = await db.scalar(
            select(func.max(Clue.position)).where(Clue.game_id == game.id)
        )
        clue = Clue(
            game_id=game.id,
            position=(max_position or 0) + 1,
            title=payload.title.strip(),
            content=payload.content.strip(),
            code=normalize_code(payload.code),
            code_fingerprint=fingerprint,
        )
        db.add(clue)
        await db.flush()
        db.add(
            audit(
                request,
                action="clue.created",
                entity_type="clue",
                entity_id=str(clue.id),
                after={"game_id": str(game.id), "position": clue.position},
            )
        )
        return clue_json(clue), 201


@admin_bp.patch("/clues/<clue_id:uuid>")
@login_required(admin=True)
async def update_clue(request: Request, clue_id: UUID):
    payload = ClueUpdate.model_validate(request.json or {})
    changes = payload.model_dump(exclude_unset=True)
    async with request.app.ctx.db.session() as db:
        clue = await db.get(Clue, clue_id)
        if not clue:
            raise NotFound("Clue not found")
        before = {"title": clue.title, "content": clue.content}
        if "code" in changes:
            submitted_code = changes.pop("code")
            fingerprint = fingerprint_code(submitted_code, request.app.ctx.settings)
            if not await code_available(db, fingerprint, excluding=clue.id):
                raise SanicException("That clue code is already in use", status_code=409)
            clue.code = normalize_code(submitted_code)
            clue.code_fingerprint = fingerprint
        for key, value in changes.items():
            setattr(clue, key, value.strip() if isinstance(value, str) else value)
        await db.flush()
        after = {"title": clue.title, "content": clue.content}
        db.add(
            audit(
                request,
                action="clue.updated",
                entity_type="clue",
                entity_id=str(clue.id),
                before=before,
                after=after,
            )
        )
        clue_media = list(
            (await db.scalars(select(ClueMedia).where(ClueMedia.clue_id == clue.id))).all()
        )
        hints = list(
            (
                await db.scalars(
                    select(Hint).where(Hint.clue_id == clue.id).order_by(Hint.position)
                )
            ).all()
        )
        hint_media = list(
            (
                await db.scalars(
                    select(HintMedia).where(HintMedia.hint_id.in_([hint.id for hint in hints]))
                )
            ).all()
        )
        media_by_hint: dict[UUID, list[HintMedia]] = {}
        for media in hint_media:
            media_by_hint.setdefault(media.hint_id, []).append(media)
        return clue_json(
            clue,
            clue_media,
            [hint_json(hint, media_by_hint.get(hint.id)) for hint in hints],
        )


@admin_bp.post("/clues/<clue_id:uuid>/hints")
@login_required(admin=True)
async def create_hint(request: Request, clue_id: UUID):
    payload = HintCreate.model_validate(request.json or {})
    text = payload.text.strip() if payload.text and payload.text.strip() else None
    async with request.app.ctx.db.session() as db:
        clue = await db.get(Clue, clue_id)
        if not clue:
            raise NotFound("Clue not found")
        max_position = await db.scalar(
            select(func.max(Hint.position)).where(Hint.clue_id == clue.id)
        )
        hint = Hint(
            clue_id=clue.id,
            position=(max_position or 0) + 1,
            text=text,
        )
        db.add(hint)
        await db.flush()
        db.add(
            audit(
                request,
                action="hint.created",
                entity_type="hint",
                entity_id=str(hint.id),
                after={
                    "clue_id": str(clue.id),
                    "position": hint.position,
                    "has_text": hint.text is not None,
                },
            )
        )
        return hint_json(hint), 201


@admin_bp.patch("/hints/<hint_id:uuid>")
@login_required(admin=True)
async def update_hint(request: Request, hint_id: UUID):
    payload = HintUpdate.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        hint = await db.get(Hint, hint_id)
        if not hint:
            raise NotFound("Hint not found")
        before = {"text": hint.text}
        if "text" in payload.model_fields_set:
            hint.text = payload.text.strip() if payload.text and payload.text.strip() else None
        await db.flush()
        db.add(
            audit(
                request,
                action="hint.updated",
                entity_type="hint",
                entity_id=str(hint.id),
                before=before,
                after={"text": hint.text},
            )
        )
        media = list(
            (await db.scalars(select(HintMedia).where(HintMedia.hint_id == hint.id))).all()
        )
        return hint_json(hint, media)


@admin_bp.post("/clues/<clue_id:uuid>/hints/reorder")
@login_required(admin=True)
async def reorder_hints(request: Request, clue_id: UUID):
    payload = HintReorder.model_validate(request.json or {})
    try:
        ids = [UUID(value) for value in payload.hint_ids]
    except ValueError as error:
        raise InvalidUsage("One or more hint IDs are invalid") from error
    if len(ids) != len(set(ids)):
        raise InvalidUsage("Each hint must appear exactly once")
    async with request.app.ctx.db.session() as db:
        hints = list(
            (
                await db.scalars(
                    select(Hint)
                    .where(Hint.clue_id == clue_id)
                    .order_by(Hint.position)
                    .with_for_update()
                )
            ).all()
        )
        if not hints:
            raise NotFound("Clue hints not found")
        if set(ids) != {hint.id for hint in hints}:
            raise InvalidUsage("The order must include every hint for the clue")
        by_id = {hint.id: hint for hint in hints}
        offset = len(hints) + 1000
        for hint in hints:
            hint.position += offset
        await db.flush()
        for position, hint_id in enumerate(ids, start=1):
            by_id[hint_id].position = position
        db.add(
            audit(
                request,
                action="hints.reordered",
                entity_type="clue",
                entity_id=str(clue_id),
                after={"hint_ids": payload.hint_ids},
            )
        )
        return {"hint_ids": payload.hint_ids}


@admin_bp.delete("/hints/<hint_id:uuid>")
@login_required(admin=True)
async def delete_hint(request: Request, hint_id: UUID):
    async with request.app.ctx.db.session() as db:
        hint = await db.get(Hint, hint_id)
        if not hint:
            raise NotFound("Hint not found")
        clue_id = hint.clue_id
        position = hint.position
        attached_media = list(
            (
                await db.execute(
                    select(HintMedia.media_type, HintMedia.provider_key).where(
                        HintMedia.hint_id == hint.id
                    )
                )
            ).tuples()
        )
        await db.delete(hint)
        await db.flush()
        affected = list(
            (
                await db.scalars(
                    select(Hint)
                    .where(Hint.clue_id == clue_id, Hint.position > position)
                    .order_by(Hint.position)
                    .with_for_update()
                )
            ).all()
        )
        original_positions = {item.id: item.position for item in affected}
        offset = len(affected) + 1000
        for item in affected:
            item.position += offset
        await db.flush()
        for item in affected:
            item.position = original_positions[item.id] - 1
        db.add(
            audit(
                request,
                action="hint.deleted",
                entity_type="hint",
                entity_id=str(hint_id),
                before={"clue_id": str(clue_id), "position": position},
            )
        )
    for attached_type, provider_key in attached_media:
        await delete_provider_media(request, attached_type, provider_key)
    return {"deleted": True}


@admin_bp.put("/clues/<clue_id:uuid>/media/<media_type:str>")
@login_required(admin=True)
async def upload_clue_media(
    request: Request,
    clue_id: UUID,
    media_type: str,
):
    try:
        selected_type = MediaType(media_type)
    except ValueError as error:
        raise NotFound("Media type not found") from error
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extension = MEDIA_CONTENT_TYPES[selected_type].get(content_type)
    if not extension:
        allowed = ", ".join(MEDIA_CONTENT_TYPES[selected_type])
        raise InvalidUsage(f"Unsupported {selected_type.value} type. Use {allowed}")
    content = request.body
    size_bytes = len(content)
    if not content:
        raise InvalidUsage("The selected media file is empty")
    max_bytes = (
        request.app.ctx.settings.photo_max_bytes
        if selected_type == MediaType.photo
        else request.app.ctx.settings.video_max_bytes
    )
    if size_bytes > max_bytes:
        limit_mib = max_bytes // (1024 * 1024)
        raise SanicException(
            f"{selected_type.value.title()} files cannot exceed {limit_mib} MiB",
            status_code=413,
        )
    if not valid_media_signature(selected_type, content_type, content[:32]):
        raise InvalidUsage(f"The uploaded file content is not a valid {selected_type.value}")

    supplied_name = unquote(request.headers.get("x-file-name", ""))
    original_filename = (
        "".join(
            character
            for character in supplied_name.replace("\\", "/").rsplit("/", 1)[-1]
            if ord(character) >= 32
        )[:255]
        or f"clue-{selected_type.value}{extension}"
    )

    async with request.app.ctx.db.session() as db:
        if not await db.get(Clue, clue_id):
            raise NotFound("Clue not found")

    logger.info(
        "event=media_upload_started request_id=%s clue_id=%s media_type=%s "
        "size_bytes=%s actor_id=%s",
        request.ctx.request_id,
        clue_id,
        selected_type.value,
        size_bytes,
        request.ctx.user.id,
    )
    provider_key = None
    try:
        if selected_type == MediaType.photo:
            provider_key = f"photos/{clue_id}/{uuid4().hex}{extension}"
            await request.app.ctx.media.upload_photo(
                provider_key,
                content,
                content_type,
            )
            actual_size = size_bytes
            status = "ready"
        else:
            provider_key = await request.app.ctx.media.upload_video(
                clue_id=str(clue_id),
                original_filename=original_filename,
                content=content,
                content_type=content_type,
            )
            video = await request.app.ctx.media.video_details(provider_key)
            actual_size = video.size_bytes or size_bytes
            await request.app.ctx.media.secure_video(provider_key)
            status = video.status
    except MediaProviderError as error:
        logger.exception(
            "event=media_upload_failed request_id=%s clue_id=%s media_type=%s size_bytes=%s",
            request.ctx.request_id,
            clue_id,
            selected_type.value,
            size_bytes,
        )
        await delete_provider_media(request, selected_type, provider_key)
        raise SanicException(str(error), status_code=502) from error

    old_provider_key = None
    created = False
    try:
        async with request.app.ctx.db.session() as db:
            clue = await db.scalar(select(Clue).where(Clue.id == clue_id).with_for_update())
            if not clue:
                raise NotFound("Clue not found")
            media = await db.scalar(
                select(ClueMedia)
                .where(
                    ClueMedia.clue_id == clue.id,
                    ClueMedia.media_type == selected_type,
                )
                .with_for_update()
            )
            before = media_audit_json(media) if media else None
            if media:
                old_provider_key = media.provider_key
                media.provider_key = provider_key
                media.original_filename = original_filename
                media.content_type = content_type
                media.size_bytes = actual_size
                media.status = status
                media.created_by_id = request.ctx.user.id
            else:
                created = True
                media = ClueMedia(
                    clue_id=clue.id,
                    media_type=selected_type,
                    provider_key=provider_key,
                    original_filename=original_filename,
                    content_type=content_type,
                    size_bytes=actual_size,
                    status=status,
                    created_by_id=request.ctx.user.id,
                )
                db.add(media)
            await db.flush()
            db.add(
                audit(
                    request,
                    action=("clue.media_attached" if created else "clue.media_replaced"),
                    entity_type="clue",
                    entity_id=str(clue.id),
                    before=before,
                    after=media_audit_json(media),
                )
            )
    except Exception:
        await delete_provider_media(request, selected_type, provider_key)
        raise
    if old_provider_key and old_provider_key != provider_key:
        await delete_provider_media(request, selected_type, old_provider_key)
    logger.info(
        "event=media_upload_completed request_id=%s clue_id=%s media_id=%s "
        "media_type=%s size_bytes=%s provider_status=%s operation=%s actor_id=%s",
        request.ctx.request_id,
        clue_id,
        media.id,
        selected_type.value,
        actual_size,
        status,
        "attached" if created else "replaced",
        request.ctx.user.id,
    )
    return media_json(media), 201 if created else 200


@admin_bp.delete("/clues/<clue_id:uuid>/media/<media_type:str>")
@login_required(admin=True)
async def delete_clue_media(request: Request, clue_id: UUID, media_type: str):
    try:
        selected_type = MediaType(media_type)
    except ValueError as error:
        raise NotFound("Media type not found") from error
    async with request.app.ctx.db.session() as db:
        clue = await db.get(Clue, clue_id)
        if not clue:
            raise NotFound("Clue not found")
        media = await db.scalar(
            select(ClueMedia)
            .where(
                ClueMedia.clue_id == clue.id,
                ClueMedia.media_type == selected_type,
            )
            .with_for_update()
        )
        if not media:
            raise NotFound(f"Clue {selected_type.value} not found")
        provider_key = media.provider_key
        before = media_audit_json(media)
        await db.delete(media)
        db.add(
            audit(
                request,
                action="clue.media_removed",
                entity_type="clue",
                entity_id=str(clue.id),
                before=before,
            )
        )
    await delete_provider_media(request, selected_type, provider_key)
    logger.info(
        "event=media_removed request_id=%s clue_id=%s media_id=%s media_type=%s actor_id=%s",
        request.ctx.request_id,
        clue_id,
        media.id,
        selected_type.value,
        request.ctx.user.id,
    )
    return {"deleted": True}


@admin_bp.put("/hints/<hint_id:uuid>/media/<media_type:str>")
@login_required(admin=True)
async def upload_hint_media(
    request: Request,
    hint_id: UUID,
    media_type: str,
):
    try:
        selected_type = MediaType(media_type)
    except ValueError as error:
        raise NotFound("Media type not found") from error
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extension = MEDIA_CONTENT_TYPES[selected_type].get(content_type)
    if not extension:
        allowed = ", ".join(MEDIA_CONTENT_TYPES[selected_type])
        raise InvalidUsage(f"Unsupported {selected_type.value} type. Use {allowed}")
    content = request.body
    size_bytes = len(content)
    if not content:
        raise InvalidUsage("The selected media file is empty")
    max_bytes = (
        request.app.ctx.settings.photo_max_bytes
        if selected_type == MediaType.photo
        else request.app.ctx.settings.video_max_bytes
    )
    if size_bytes > max_bytes:
        limit_mib = max_bytes // (1024 * 1024)
        raise SanicException(
            f"{selected_type.value.title()} files cannot exceed {limit_mib} MiB",
            status_code=413,
        )
    if not valid_media_signature(selected_type, content_type, content[:32]):
        raise InvalidUsage(f"The uploaded file content is not a valid {selected_type.value}")

    supplied_name = unquote(request.headers.get("x-file-name", ""))
    original_filename = (
        "".join(
            character
            for character in supplied_name.replace("\\", "/").rsplit("/", 1)[-1]
            if ord(character) >= 32
        )[:255]
        or f"hint-{selected_type.value}{extension}"
    )

    async with request.app.ctx.db.session() as db:
        if not await db.get(Hint, hint_id):
            raise NotFound("Hint not found")

    logger.info(
        "event=hint_media_upload_started request_id=%s hint_id=%s media_type=%s "
        "size_bytes=%s actor_id=%s",
        request.ctx.request_id,
        hint_id,
        selected_type.value,
        size_bytes,
        request.ctx.user.id,
    )
    provider_key = None
    try:
        if selected_type == MediaType.photo:
            provider_key = f"hint-photos/{hint_id}/{uuid4().hex}{extension}"
            await request.app.ctx.media.upload_photo(
                provider_key,
                content,
                content_type,
            )
            actual_size = size_bytes
            status = "ready"
        else:
            provider_key = await request.app.ctx.media.upload_video(
                clue_id=f"hint-{hint_id}",
                original_filename=original_filename,
                content=content,
                content_type=content_type,
            )
            video = await request.app.ctx.media.video_details(provider_key)
            actual_size = video.size_bytes or size_bytes
            await request.app.ctx.media.secure_video(provider_key)
            status = video.status
    except MediaProviderError as error:
        logger.exception(
            "event=hint_media_upload_failed request_id=%s hint_id=%s media_type=%s size_bytes=%s",
            request.ctx.request_id,
            hint_id,
            selected_type.value,
            size_bytes,
        )
        await delete_provider_media(request, selected_type, provider_key)
        raise SanicException(str(error), status_code=502) from error

    old_provider_key = None
    created = False
    try:
        async with request.app.ctx.db.session() as db:
            hint = await db.scalar(select(Hint).where(Hint.id == hint_id).with_for_update())
            if not hint:
                raise NotFound("Hint not found")
            media = await db.scalar(
                select(HintMedia)
                .where(
                    HintMedia.hint_id == hint.id,
                    HintMedia.media_type == selected_type,
                )
                .with_for_update()
            )
            before = media_audit_json(media) if media else None
            if media:
                old_provider_key = media.provider_key
                media.provider_key = provider_key
                media.original_filename = original_filename
                media.content_type = content_type
                media.size_bytes = actual_size
                media.status = status
                media.created_by_id = request.ctx.user.id
            else:
                created = True
                media = HintMedia(
                    hint_id=hint.id,
                    media_type=selected_type,
                    provider_key=provider_key,
                    original_filename=original_filename,
                    content_type=content_type,
                    size_bytes=actual_size,
                    status=status,
                    created_by_id=request.ctx.user.id,
                )
                db.add(media)
            await db.flush()
            db.add(
                audit(
                    request,
                    action=("hint.media_attached" if created else "hint.media_replaced"),
                    entity_type="hint",
                    entity_id=str(hint.id),
                    before=before,
                    after=media_audit_json(media),
                )
            )
    except Exception:
        await delete_provider_media(request, selected_type, provider_key)
        raise
    if old_provider_key and old_provider_key != provider_key:
        await delete_provider_media(request, selected_type, old_provider_key)
    logger.info(
        "event=hint_media_upload_completed request_id=%s hint_id=%s media_id=%s "
        "media_type=%s size_bytes=%s provider_status=%s operation=%s actor_id=%s",
        request.ctx.request_id,
        hint_id,
        media.id,
        selected_type.value,
        actual_size,
        status,
        "attached" if created else "replaced",
        request.ctx.user.id,
    )
    return media_json(media), 201 if created else 200


@admin_bp.delete("/hints/<hint_id:uuid>/media/<media_type:str>")
@login_required(admin=True)
async def delete_hint_media(request: Request, hint_id: UUID, media_type: str):
    try:
        selected_type = MediaType(media_type)
    except ValueError as error:
        raise NotFound("Media type not found") from error
    async with request.app.ctx.db.session() as db:
        hint = await db.get(Hint, hint_id)
        if not hint:
            raise NotFound("Hint not found")
        media = await db.scalar(
            select(HintMedia)
            .where(
                HintMedia.hint_id == hint.id,
                HintMedia.media_type == selected_type,
            )
            .with_for_update()
        )
        if not media:
            raise NotFound(f"Hint {selected_type.value} not found")
        provider_key = media.provider_key
        before = media_audit_json(media)
        await db.delete(media)
        db.add(
            audit(
                request,
                action="hint.media_removed",
                entity_type="hint",
                entity_id=str(hint.id),
                before=before,
            )
        )
    await delete_provider_media(request, selected_type, provider_key)
    return {"deleted": True}


@admin_bp.post("/games/<game_id:uuid>/clues/reorder")
@login_required(admin=True)
async def reorder_clues(request: Request, game_id: UUID):
    payload = ClueReorder.model_validate(request.json or {})
    try:
        ids = [UUID(value) for value in payload.clue_ids]
    except ValueError as error:
        raise InvalidUsage("One or more clue IDs are invalid") from error
    if len(ids) != len(set(ids)):
        raise InvalidUsage("Each clue must appear exactly once")
    async with request.app.ctx.db.session() as db:
        clues = list(
            (
                await db.scalars(
                    select(Clue)
                    .where(Clue.game_id == game_id)
                    .order_by(Clue.position)
                    .with_for_update()
                )
            ).all()
        )
        if set(ids) != {clue.id for clue in clues}:
            raise InvalidUsage("The order must include every clue in the game")
        by_id = {clue.id: clue for clue in clues}
        offset = len(clues) + 1000
        for clue in clues:
            clue.position += offset
        await db.flush()
        for position, clue_id in enumerate(ids, start=1):
            by_id[clue_id].position = position
        db.add(
            audit(
                request,
                action="clues.reordered",
                entity_type="game",
                entity_id=str(game_id),
                after={"clue_ids": payload.clue_ids},
            )
        )
        return {"clue_ids": payload.clue_ids}


@admin_bp.delete("/clues/<clue_id:uuid>")
@login_required(admin=True)
async def delete_clue(request: Request, clue_id: UUID):
    async with request.app.ctx.db.session() as db:
        clue = await db.get(Clue, clue_id)
        if not clue:
            raise NotFound("Clue not found")
        game_id = clue.game_id
        position = clue.position
        attached_media = list(
            (
                await db.execute(
                    select(ClueMedia.media_type, ClueMedia.provider_key).where(
                        ClueMedia.clue_id == clue.id
                    )
                )
            ).tuples()
        )
        attached_hint_media = list(
            (
                await db.execute(
                    select(HintMedia.media_type, HintMedia.provider_key)
                    .join(Hint, Hint.id == HintMedia.hint_id)
                    .where(Hint.clue_id == clue.id)
                )
            ).tuples()
        )
        await db.delete(clue)
        await db.flush()
        affected = list(
            (
                await db.scalars(
                    select(Clue)
                    .where(Clue.game_id == game_id, Clue.position > position)
                    .order_by(Clue.position)
                    .with_for_update()
                )
            ).all()
        )
        original_positions = {item.id: item.position for item in affected}
        offset = len(affected) + 1000
        for item in affected:
            item.position += offset
        await db.flush()
        for item in affected:
            item.position = original_positions[item.id] - 1
        db.add(
            audit(
                request,
                action="clue.deleted",
                entity_type="clue",
                entity_id=str(clue_id),
                before={"game_id": str(game_id), "position": position},
            )
        )
    for attached_type, provider_key in [*attached_media, *attached_hint_media]:
        await delete_provider_media(request, attached_type, provider_key)
    return {"deleted": True}


@admin_bp.delete("/game-players/<membership_id:uuid>/progress")
@login_required(admin=True)
async def reset_progress(request: Request, membership_id: UUID):
    payload = ProgressReset.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        membership = await db.get(GamePlayer, membership_id)
        if not membership:
            raise NotFound("Game assignment not found")
        target_clue = None
        if payload.clue_id:
            target_clue = await db.get(Clue, payload.clue_id)
            if not target_clue or target_clue.game_id != membership.game_id:
                raise InvalidUsage("That clue does not belong to this game")
            target_completion = await db.scalar(
                select(ClueCompletion.id).where(
                    ClueCompletion.game_player_id == membership.id,
                    ClueCompletion.clue_id == target_clue.id,
                )
            )
            if not target_completion:
                raise InvalidUsage("The player has not completed that clue")
        completion_count = await db.scalar(
            select(func.count(ClueCompletion.id)).where(
                ClueCompletion.game_player_id == membership.id
            )
        )
        reset_filter = ClueCompletion.game_player_id == membership.id
        if target_clue:
            reset_filter = reset_filter & ClueCompletion.clue_id.in_(
                select(Clue.id).where(
                    Clue.game_id == membership.game_id,
                    Clue.position >= target_clue.position,
                )
            )
        await db.execute(delete(ClueCompletion).where(reset_filter))
        hint_reveal_filter = HintReveal.game_player_id == membership.id
        if target_clue:
            hint_reveal_filter = hint_reveal_filter & HintReveal.hint_id.in_(
                select(Hint.id)
                .join(Clue, Clue.id == Hint.clue_id)
                .where(
                    Clue.game_id == membership.game_id,
                    Clue.position >= target_clue.position,
                )
            )
        await db.execute(delete(HintReveal).where(hint_reveal_filter))
        answer_reveal_filter = ClueAnswerReveal.game_player_id == membership.id
        if target_clue:
            answer_reveal_filter = answer_reveal_filter & ClueAnswerReveal.clue_id.in_(
                select(Clue.id).where(
                    Clue.game_id == membership.game_id,
                    Clue.position >= target_clue.position,
                )
            )
        await db.execute(delete(ClueAnswerReveal).where(answer_reveal_filter))
        await db.flush()
        remaining_count = (
            await db.scalar(
                select(func.count(ClueCompletion.id)).where(
                    ClueCompletion.game_player_id == membership.id
                )
            )
            or 0
        )
        db.add(
            audit(
                request,
                action="player.progress_reset",
                entity_type="game_player",
                entity_id=str(membership.id),
                before={"completion_count": completion_count or 0},
                after={
                    "completion_count": remaining_count,
                    "game_id": str(membership.game_id),
                    "user_id": str(membership.user_id),
                    "target_clue_id": str(target_clue.id) if target_clue else None,
                    "target_position": target_clue.position if target_clue else None,
                },
                reason=payload.reason.strip(),
            )
        )
        return {
            "reset": True,
            "completion_count": remaining_count,
            "target_clue_id": str(target_clue.id) if target_clue else None,
        }


@admin_bp.put("/game-players/<membership_id:uuid>/progress")
@login_required(admin=True)
async def advance_progress(request: Request, membership_id: UUID):
    payload = ProgressAdvance.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        membership = await db.scalar(
            select(GamePlayer).where(GamePlayer.id == membership_id).with_for_update()
        )
        if not membership:
            raise NotFound("Game assignment not found")
        clues = list(
            (
                await db.scalars(
                    select(Clue).where(Clue.game_id == membership.game_id).order_by(Clue.position)
                )
            ).all()
        )
        target_index = next(
            (index for index, clue in enumerate(clues) if clue.id == payload.clue_id),
            None,
        )
        if target_index is None:
            raise InvalidUsage("That clue does not belong to this game")
        completed_ids = set(
            (
                await db.scalars(
                    select(ClueCompletion.clue_id).where(
                        ClueCompletion.game_player_id == membership.id
                    )
                )
            ).all()
        )
        first_incomplete = next(
            (index for index, clue in enumerate(clues) if clue.id not in completed_ids),
            len(clues),
        )
        if target_index <= first_incomplete:
            raise InvalidUsage("Choose a clue after the player's current clue")

        now = datetime.now(UTC)
        added_clues = [clue for clue in clues[:target_index] if clue.id not in completed_ids]
        db.add_all(
            [
                ClueCompletion(
                    game_player_id=membership.id,
                    clue_id=clue.id,
                    completed_at=now,
                )
                for clue in added_clues
            ]
        )
        await db.flush()
        completion_count = len(completed_ids) + len(added_clues)
        target_clue = clues[target_index]
        db.add(
            audit(
                request,
                action="player.progress_advanced",
                entity_type="game_player",
                entity_id=str(membership.id),
                before={"completion_count": len(completed_ids)},
                after={
                    "completion_count": completion_count,
                    "game_id": str(membership.game_id),
                    "user_id": str(membership.user_id),
                    "target_clue_id": str(target_clue.id),
                    "target_position": target_clue.position,
                    "added_clue_ids": [str(clue.id) for clue in added_clues],
                },
                reason=payload.reason.strip(),
            )
        )
        return {
            "advanced": True,
            "completion_count": completion_count,
            "target_clue_id": str(target_clue.id),
        }
