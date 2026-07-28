from __future__ import annotations

from sqlalchemy import select

from pdcscavengerhunt.models import AuditEvent, Clue, Game, GamePlayer, User

from .conftest import auth


async def test_admin_can_configure_game_players_and_clues(app, admin):
    cookies, headers = auth(app, admin)
    async with app.ctx.db.session() as db:
        player = User(
            username="configured-player",
            normalized_username="configured-player",
            display_name="Configured Player",
        )
        db.add(player)
        await db.flush()

    _request, created = await app.asgi_client.post(
        "/api/v1/admin/games",
        json={
            "title": "Configured Hunt",
            "description": "A test hunt",
            "instructions": "Stay on the sidewalk.",
        },
        cookies=cookies,
        headers=headers,
    )
    assert created.status == 201
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

    _request, opened = await app.asgi_client.patch(
        f"/api/v1/admin/games/{game_id}",
        json={"status": "open"},
        cookies=cookies,
        headers=headers,
    )
    assert opened.status == 200
    assert opened.json["status"] == "open"

    async with app.ctx.db.session() as db:
        game = await db.get(Game, game_id)
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
