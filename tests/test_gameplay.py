from __future__ import annotations

from sqlalchemy import select

from pdcscavengerhunt.models import Clue, ClueCompletion, Game, GamePlayer, User
from pdcscavengerhunt.security import fingerprint_code, hash_password

from .conftest import auth


async def make_game(app, admin):
    player = User(
        email_address="player@example.com",
        normalized_email_address="player@example.com",
        full_name="Test Player",
        password_hash=hash_password("test-player-password"),
    )
    stranger = User(
        email_address="stranger@example.com",
        normalized_email_address="stranger@example.com",
        full_name="Stranger",
        password_hash=hash_password("test-stranger-password"),
    )
    game = Game(
        title="Downtown Hunt",
        closing_message="Thanks for playing!",
        status="open",
        created_by_id=admin.id,
    )
    async with app.ctx.db.session() as db:
        db.add_all([player, stranger, game])
        await db.flush()
        membership = GamePlayer(
            game_id=game.id,
            user_id=player.id,
            assigned_by_id=admin.id,
        )
        db.add(membership)
        db.add_all(
            [
                Clue(
                    game_id=game.id,
                    position=1,
                    title="First Reveal",
                    content="Walk to the clock.",
                    code="CLOCK-1",
                    code_fingerprint=fingerprint_code("CLOCK-1", app.ctx.settings),
                ),
                Clue(
                    game_id=game.id,
                    position=2,
                    title="Second Reveal",
                    content="Find the mural.",
                    code="MURAL-2",
                    code_fingerprint=fingerprint_code("MURAL-2", app.ctx.settings),
                ),
            ]
        )
    return player, stranger, game


async def test_game_state_exposes_current_clue_but_not_its_answer(app, admin):
    player, _stranger, game = await make_game(app, admin)
    cookies, _headers = auth(app, player)
    _request, response = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=cookies,
    )
    assert response.status == 200
    assert response.json["closing_message"] is None
    assert response.json["clues"] == [
        {
            "id": response.json["clues"][0]["id"],
            "position": 1,
            "status": "current",
            "clue": "First Reveal",
            "photo": None,
            "video": None,
        },
        {"position": 2, "status": "locked"},
    ]
    assert "Walk to the clock." not in response.text
    assert "Find the mural." not in response.text
    assert "CLOCK-1" not in response.text
    assert "MURAL-2" not in response.text


async def test_player_must_complete_clues_in_order(app, admin):
    player, _stranger, game = await make_game(app, admin)
    cookies, headers = auth(app, player)
    async with app.ctx.db.session() as db:
        clues = list(
            (
                await db.scalars(
                    select(Clue).where(Clue.game_id == game.id).order_by(Clue.position)
                )
            ).all()
        )

    _request, out_of_order = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/complete",
        json={"code": "MURAL-2"},
        cookies=cookies,
        headers=headers,
    )
    assert out_of_order.status == 409

    _request, wrong = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/complete",
        json={"code": "WRONG"},
        cookies=cookies,
        headers=headers,
    )
    assert wrong.status == 400
    assert "Walk to the clock." not in wrong.text

    _request, first = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/complete",
        json={"code": " clock-1 "},
        cookies=cookies,
        headers=headers,
    )
    assert first.status == 200
    assert first.json["created"] is True
    assert first.json["game"]["clues"][0]["answer"] == "Walk to the clock."
    assert first.json["game"]["clues"][1]["status"] == "current"
    assert first.json["game"]["clues"][1]["clue"] == "Second Reveal"
    assert "answer" not in first.json["game"]["clues"][1]

    _request, duplicate = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/complete",
        json={"code": "CLOCK-1"},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate.status == 200
    assert duplicate.json["created"] is False

    _request, second = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/complete",
        json={"code": "mural-2"},
        cookies=cookies,
        headers=headers,
    )
    assert second.status == 200
    assert second.json["game"]["complete"] is True
    assert second.json["game"]["closing_message"] == "Thanks for playing!"

    async with app.ctx.db.session() as db:
        assert await db.scalar(select(ClueCompletion).limit(1))
        assert len(list((await db.scalars(select(ClueCompletion))).all())) == 2


async def test_unassigned_user_cannot_access_game(app, admin):
    _player, stranger, game = await make_game(app, admin)
    cookies, _headers = auth(app, stranger)
    _request, response = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=cookies,
    )
    assert response.status == 404


async def test_closed_game_is_read_only(app, admin):
    player, _stranger, game = await make_game(app, admin)
    async with app.ctx.db.session() as db:
        stored = await db.get(Game, game.id)
        stored.status = "closed"
        clue = await db.scalar(select(Clue).where(Clue.game_id == game.id))
    cookies, headers = auth(app, player)
    _request, response = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/complete",
        json={"code": "CLOCK-1"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status == 403
