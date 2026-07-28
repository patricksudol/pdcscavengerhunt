from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from pdcscavengerhunt.models import (
    AuditEvent,
    Clue,
    ClueCompletion,
    Game,
    GamePlayer,
    User,
)
from pdcscavengerhunt.security import fingerprint_code

from .conftest import auth


async def test_admin_can_configure_game_players_and_clues(app, admin):
    cookies, headers = auth(app, admin)
    async with app.ctx.db.session() as db:
        player = User(
            email_address="configured-player@example.com",
            normalized_email_address="configured-player@example.com",
            full_name="Configured Player",
        )
        db.add(player)
        await db.flush()

    _request, created = await app.asgi_client.post(
        "/api/v1/admin/games",
        json={
            "title": "Configured Hunt",
            "description": "A test hunt",
            "instructions": "Stay on the sidewalk.",
            "closing_message": "Thanks for playing!",
        },
        cookies=cookies,
        headers=headers,
    )
    assert created.status == 201
    assert created.json["closing_message"] == "Thanks for playing!"
    game_id = created.json["id"]

    _request, membership = await app.asgi_client.put(
        f"/api/v1/admin/games/{game_id}/players",
        json={"user_ids": [str(player.id)]},
        cookies=cookies,
        headers=headers,
    )
    assert membership.status == 200

    clue_ids = []
    for title, code in (("One", "UNIQUE-ONE"), ("Two", "UNIQUE-TWO")):
        _request, clue = await app.asgi_client.post(
            f"/api/v1/admin/games/{game_id}/clues",
            json={"title": title, "content": f"Content {title}", "code": code},
            cookies=cookies,
            headers=headers,
        )
        assert clue.status == 201
        assert clue.json["code"] == code
        clue_ids.append(clue.json["id"])

    _request, duplicate_code = await app.asgi_client.post(
        f"/api/v1/admin/games/{game_id}/clues",
        json={"title": "Three", "content": "Content", "code": "unique-one"},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate_code.status == 409

    _request, reordered = await app.asgi_client.post(
        f"/api/v1/admin/games/{game_id}/clues/reorder",
        json={"clue_ids": list(reversed(clue_ids))},
        cookies=cookies,
        headers=headers,
    )
    assert reordered.status == 200

    _request, detail = await app.asgi_client.get(
        f"/api/v1/admin/games/{game_id}",
        cookies=cookies,
        headers=headers,
    )
    assert detail.status == 200
    assert {clue["code"] for clue in detail.json["clues"]} == {
        "UNIQUE-ONE",
        "UNIQUE-TWO",
    }

    _request, opened = await app.asgi_client.patch(
        f"/api/v1/admin/games/{game_id}",
        json={"status": "open"},
        cookies=cookies,
        headers=headers,
    )
    assert opened.status == 200
    assert opened.json["status"] == "open"

    async with app.ctx.db.session() as db:
        game = await db.get(Game, UUID(game_id))
        membership_row = await db.scalar(
            select(GamePlayer).where(GamePlayer.game_id == game.id)
        )
        clues = list(
            (
                await db.scalars(
                    select(Clue).where(Clue.game_id == game.id).order_by(Clue.position)
                )
            ).all()
        )
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert membership_row.user_id == player.id
        assert game.closing_message == "Thanks for playing!"
        assert [str(clue.id) for clue in clues] == list(reversed(clue_ids))
        expected_actions = {
            "game.created",
            "game.players_updated",
            "clue.created",
            "clues.reordered",
        }
        assert expected_actions <= actions


async def test_admin_cannot_remove_own_admin_access(app, admin):
    cookies, headers = auth(app, admin)
    for changes in ({"is_admin": False}, {"active": False}):
        _request, response = await app.asgi_client.patch(
            f"/api/v1/admin/users/{admin.id}",
            json=changes,
            cookies=cookies,
            headers=headers,
        )
        assert response.status == 400


async def test_admin_game_detail_includes_clue_completion_timestamps(app, admin):
    completed_at = datetime(2026, 7, 28, 14, 35, tzinfo=UTC)
    async with app.ctx.db.session() as db:
        player = User(
            email_address="timestamp-player@example.com",
            normalized_email_address="timestamp-player@example.com",
            full_name="Timestamp Player",
        )
        game = Game(title="Timestamp Game", status="open")
        db.add_all([player, game])
        await db.flush()
        membership = GamePlayer(game_id=game.id, user_id=player.id)
        clue = Clue(
            game_id=game.id,
            position=1,
            title="Timestamp Clue",
            content="Timestamp content",
            code_fingerprint=fingerprint_code("TIMESTAMP-CODE", app.ctx.settings),
        )
        db.add_all([membership, clue])
        await db.flush()
        db.add(
            ClueCompletion(
                game_player_id=membership.id,
                clue_id=clue.id,
                completed_at=completed_at,
            )
        )
        game_id = game.id
        clue_id = clue.id

    cookies, headers = auth(app, admin)
    _request, response = await app.asgi_client.get(
        f"/api/v1/admin/games/{game_id}",
        cookies=cookies,
        headers=headers,
    )

    assert response.status == 200
    player_progress = response.json["players"][0]
    assert player_progress["completed_clue_ids"] == [str(clue_id)]
    assert player_progress["completions"] == [
        {
            "clue_id": str(clue_id),
            "completed_at": completed_at.isoformat(),
        }
    ]


async def test_admin_can_edit_full_name_and_email_address(app, admin):
    async with app.ctx.db.session() as db:
        player = User(
            email_address="before@example.com",
            normalized_email_address="before@example.com",
            full_name="Before Name",
        )
        db.add(player)
        await db.flush()
        player_id = player.id

    cookies, headers = auth(app, admin)
    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/users/{player_id}",
        json={
            "email_address": "After.Name@Example.com",
            "full_name": "After Name",
        },
        cookies=cookies,
        headers=headers,
    )
    assert response.status == 200
    assert response.json["email_address"] == "After.Name@example.com"
    assert response.json["full_name"] == "After Name"

    async with app.ctx.db.session() as db:
        stored = await db.get(User, player_id)
        assert stored
        assert stored.normalized_email_address == "after.name@example.com"


async def test_admin_can_reset_player_progress_with_reason(app, admin):
    async with app.ctx.db.session() as db:
        player = User(
            email_address="reset-player@example.com",
            normalized_email_address="reset-player@example.com",
            full_name="Reset Player",
        )
        game = Game(title="Reset Game", status="open")
        db.add_all([player, game])
        await db.flush()
        membership = GamePlayer(game_id=game.id, user_id=player.id)
        clue = Clue(
            game_id=game.id,
            position=1,
            title="Reset Clue",
            content="Reset content",
            code_fingerprint=fingerprint_code("RESET-CODE", app.ctx.settings),
        )
        db.add_all([membership, clue])
        await db.flush()
        db.add(
            ClueCompletion(
                game_player_id=membership.id,
                clue_id=clue.id,
            )
        )
        membership_id = membership.id

    cookies, headers = auth(app, admin)
    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/game-players/{membership_id}/progress",
        json={"reason": "Player requested a restart"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status == 200

    async with app.ctx.db.session() as db:
        assert await db.scalar(select(ClueCompletion)) is None
        event = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "player.progress_reset")
        )
        assert event
        assert event.reason == "Player requested a restart"


async def test_admin_can_reset_player_progress_to_a_specific_clue(app, admin):
    async with app.ctx.db.session() as db:
        player = User(
            email_address="targeted-reset@example.com",
            normalized_email_address="targeted-reset@example.com",
            full_name="Targeted Reset",
        )
        game = Game(title="Targeted Reset Game", status="open")
        db.add_all([player, game])
        await db.flush()
        membership = GamePlayer(game_id=game.id, user_id=player.id)
        clues = [
            Clue(
                game_id=game.id,
                position=position,
                title=f"Clue {position}",
                content=f"Answer {position}",
                code_fingerprint=fingerprint_code(
                    f"TARGET-{position}", app.ctx.settings
                ),
            )
            for position in range(1, 4)
        ]
        db.add_all([membership, *clues])
        await db.flush()
        db.add_all(
            [
                ClueCompletion(
                    game_player_id=membership.id,
                    clue_id=clue.id,
                )
                for clue in clues
            ]
        )
        membership_id = membership.id
        target_clue_id = clues[1].id
        retained_clue_id = clues[0].id

    cookies, headers = auth(app, admin)
    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/game-players/{membership_id}/progress",
        json={
            "reason": "Return player to the second clue",
            "clue_id": str(target_clue_id),
        },
        cookies=cookies,
        headers=headers,
    )
    assert response.status == 200
    assert response.json["completion_count"] == 1
    assert response.json["target_clue_id"] == str(target_clue_id)

    async with app.ctx.db.session() as db:
        remaining_clue_ids = set(
            (
                await db.scalars(
                    select(ClueCompletion.clue_id).where(
                        ClueCompletion.game_player_id == membership_id
                    )
                )
            ).all()
        )
        assert remaining_clue_ids == {retained_clue_id}
        event = await db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "player.progress_reset",
                AuditEvent.entity_id == str(membership_id),
            )
        )
        assert event
        assert event.after["completion_count"] == 1
        assert event.after["target_position"] == 2
