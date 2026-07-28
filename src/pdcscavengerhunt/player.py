from __future__ import annotations

import hmac
from uuid import UUID

from sanic import Blueprint, Request
from sanic.exceptions import Forbidden, InvalidUsage, NotFound, SanicException
from sqlalchemy import func, select

from .models import (
    AuditEvent,
    Clue,
    ClueCompletion,
    Game,
    GamePlayer,
    GameStatus,
)
from .schemas import CodeSubmission
from .security import check_rate_limit, fingerprint_code, login_required

player_bp = Blueprint("player", url_prefix="/api/v1/player")


async def membership_for(db, game_id: UUID, user_id: UUID, *, lock: bool = False):
    query = select(GamePlayer).where(
        GamePlayer.game_id == game_id,
        GamePlayer.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    return await db.scalar(query)


async def game_state(db, game: Game, membership: GamePlayer) -> dict:
    clues = list(
        (
            await db.scalars(
                select(Clue).where(Clue.game_id == game.id).order_by(Clue.position)
            )
        ).all()
    )
    completions = list(
        (
            await db.scalars(
                select(ClueCompletion)
                .where(ClueCompletion.game_player_id == membership.id)
                .order_by(ClueCompletion.completed_at)
            )
        ).all()
    )
    completion_map = {completion.clue_id: completion for completion in completions}
    first_incomplete = next(
        (index for index, clue in enumerate(clues) if clue.id not in completion_map),
        len(clues),
    )
    clue_data = []
    for index, clue in enumerate(clues):
        completion = completion_map.get(clue.id)
        if completion:
            clue_data.append(
                {
                    "id": str(clue.id),
                    "position": clue.position,
                    "status": "completed",
                    "title": clue.title,
                    "content": clue.content,
                    "completed_at": completion.completed_at.isoformat(),
                }
            )
        elif index == first_incomplete:
            clue_data.append(
                {
                    "id": str(clue.id),
                    "position": clue.position,
                    "status": "current",
                }
            )
        else:
            clue_data.append({"position": clue.position, "status": "locked"})
    return {
        "id": str(game.id),
        "title": game.title,
        "description": game.description,
        "instructions": game.instructions,
        "status": game.status.value,
        "completed_count": len(completions),
        "clue_count": len(clues),
        "complete": bool(clues) and len(completions) == len(clues),
        "clues": clue_data,
    }


@player_bp.get("/games")
@login_required()
async def list_games(request: Request):
    async with request.app.ctx.db.session() as db:
        rows = (
            await db.execute(
                select(Game, GamePlayer)
                .join(GamePlayer, GamePlayer.game_id == Game.id)
                .where(
                    GamePlayer.user_id == request.ctx.user.id,
                    Game.status != GameStatus.draft,
                )
                .order_by(Game.created_at.desc())
            )
        ).all()
        result = []
        for game, membership in rows:
            clue_count = await db.scalar(
                select(func.count(Clue.id)).where(Clue.game_id == game.id)
            )
            completed_count = await db.scalar(
                select(func.count(ClueCompletion.id)).where(
                    ClueCompletion.game_player_id == membership.id
                )
            )
            result.append(
                {
                    "id": str(game.id),
                    "title": game.title,
                    "description": game.description,
                    "status": game.status.value,
                    "clue_count": clue_count or 0,
                    "completed_count": completed_count or 0,
                }
            )
        return result


@player_bp.get("/games/<game_id:uuid>")
@login_required()
async def get_game(request: Request, game_id: UUID):
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        membership = await membership_for(db, game_id, request.ctx.user.id)
        if not game or not membership or game.status == GameStatus.draft:
            raise NotFound("Game not found")
        return await game_state(db, game, membership)


@player_bp.post("/games/<game_id:uuid>/clues/<clue_id:uuid>/complete")
@login_required()
async def complete_clue(request: Request, game_id: UUID, clue_id: UUID):
    payload = CodeSubmission.model_validate(request.json or {})
    check_rate_limit(
        request,
        namespace="clue-code",
        identity=str(request.ctx.user.id),
        limit=request.app.ctx.settings.code_rate_limit,
    )
    async with request.app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
        membership = await membership_for(
            db, game_id, request.ctx.user.id, lock=True
        )
        if not game or not membership:
            raise NotFound("Game not found")
        if game.status != GameStatus.open:
            raise Forbidden("This game is not open for new clues")
        clues = list(
            (
                await db.scalars(
                    select(Clue)
                    .where(Clue.game_id == game_id)
                    .order_by(Clue.position)
                )
            ).all()
        )
        target = next((clue for clue in clues if clue.id == clue_id), None)
        if not target:
            raise NotFound("Clue not found")
        completed_ids = set(
            (
                await db.scalars(
                    select(ClueCompletion.clue_id).where(
                        ClueCompletion.game_player_id == membership.id
                    )
                )
            ).all()
        )
        if target.id in completed_ids:
            return {
                "created": False,
                "game": await game_state(db, game, membership),
            }
        next_clue = next((clue for clue in clues if clue.id not in completed_ids), None)
        if not next_clue or next_clue.id != target.id:
            raise SanicException("Complete the earlier clues first", status_code=409)
        submitted = fingerprint_code(payload.code, request.app.ctx.settings)
        if not hmac.compare_digest(submitted, target.code_fingerprint):
            db.add(
                AuditEvent(
                    actor_id=request.ctx.user.id,
                    action="clue.code_rejected",
                    entity_type="clue",
                    entity_id=str(target.id),
                    reason="Incorrect code",
                    request_id=request.ctx.request_id,
                )
            )
            raise InvalidUsage("That code is not correct")
        completion = ClueCompletion(
            game_player_id=membership.id,
            clue_id=target.id,
        )
        db.add(completion)
        await db.flush()
        db.add(
            AuditEvent(
                actor_id=request.ctx.user.id,
                action="clue.completed",
                entity_type="clue",
                entity_id=str(target.id),
                after={"game_id": str(game.id), "position": target.position},
                request_id=request.ctx.request_id,
            )
        )
        return {
            "created": True,
            "game": await game_state(db, game, membership),
        }

