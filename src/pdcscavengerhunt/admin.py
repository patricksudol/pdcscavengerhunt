from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, NotFound, SanicException
from sqlalchemy import delete, func, select, update

from .auth import setup_token_hash
from .models import (
    AuditEvent,
    Clue,
    ClueCompletion,
    Game,
    GamePlayer,
    PasswordSetupToken,
    User,
)
from .schemas import (
    ClueCreate,
    ClueReorder,
    ClueUpdate,
    GameCreate,
    GameUpdate,
    MembershipUpdate,
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
        open_games = await db.scalar(
            select(func.count(Game.id)).where(Game.status == "open")
        )
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


@admin_bp.post("/users")
@login_required(admin=True)
async def create_user(request: Request):
    payload = UserCreate.model_validate(request.json or {})
    normalized = normalize_email_address(str(payload.email_address))
    async with request.app.ctx.db.session() as db:
        if await db.scalar(
            select(User.id).where(User.normalized_email_address == normalized)
        ):
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
        if user.is_admin and user.active and (
            changes.get("active") is False or changes.get("is_admin") is False
        ):
            admin_count = await db.scalar(
                select(func.count(User.id)).where(
                    User.is_admin.is_(True), User.active.is_(True)
                )
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
        if (
            email_address
            or "active" in changes
            or "is_admin" in changes
        ):
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
        games = list(
            (await db.scalars(select(Game).order_by(Game.created_at.desc()))).all()
        )
        result = []
        for game in games:
            player_count = await db.scalar(
                select(func.count(GamePlayer.id)).where(GamePlayer.game_id == game.id)
            )
            clue_count = await db.scalar(
                select(func.count(Clue.id)).where(Clue.game_id == game.id)
            )
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
            completed_clue_ids = [
                completion["clue_id"] for completion in completions
            ]
            progress.append(
                {
                    "membership_id": str(membership.id),
                    "user": user_json(user),
                    "completed_count": len(completions),
                    "completed_clue_ids": completed_clue_ids,
                    "completions": completions,
                }
            )
        return {
            **game_json(
                game,
                player_count=len(members),
                clue_count=len(clues),
                completion_count=sum(item["completed_count"] for item in progress),
            ),
            "clues": [
                {
                    "id": str(clue.id),
                    "position": clue.position,
                    "title": clue.title,
                    "content": clue.content,
                    "code": clue.code,
                    "code_set": True,
                }
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
            (
                await db.scalars(
                    select(GamePlayer).where(GamePlayer.game_id == game.id)
                )
            ).all()
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
        return {
            "id": str(clue.id),
            "position": clue.position,
            "title": clue.title,
            "content": clue.content,
            "code": clue.code,
            "code_set": True,
        }, 201


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
        return {
            "id": str(clue.id),
            "position": clue.position,
            "title": clue.title,
            "content": clue.content,
            "code": clue.code,
            "code_set": True,
        }


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
