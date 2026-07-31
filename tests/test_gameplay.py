from __future__ import annotations

from sqlalchemy import select

from pdcscavengerhunt.models import (
    AuditEvent,
    Clue,
    ClueAnswerReveal,
    ClueCompletion,
    Game,
    GamePlayer,
    Hint,
    HintReveal,
    User,
)
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


async def test_game_state_exposes_all_clue_headlines_but_not_their_answers(app, admin):
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
            "status": "available",
            "clue": "First Reveal",
            "photo": None,
            "video": None,
            "hints": [],
            "can_reveal_answer": False,
        },
        {
            "id": response.json["clues"][1]["id"],
            "position": 2,
            "status": "available",
            "clue": "Second Reveal",
            "photo": None,
            "video": None,
            "hints": [],
            "can_reveal_answer": False,
        },
    ]
    assert "Walk to the clock." not in response.text
    assert "Find the mural." not in response.text
    assert "CLOCK-1" not in response.text
    assert "MURAL-2" not in response.text


async def test_player_reveals_clue_hints_in_order(app, admin):
    player, _stranger, game = await make_game(app, admin)
    async with app.ctx.db.session() as db:
        clue = await db.scalar(select(Clue).where(Clue.game_id == game.id).order_by(Clue.position))
        hints = [
            Hint(clue_id=clue.id, position=1, text="Look toward the clock tower."),
            Hint(clue_id=clue.id, position=2, text="Check beneath the blue sign."),
        ]
        db.add_all(hints)
        await db.flush()

    cookies, headers = auth(app, player)
    _request, initial = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=cookies,
    )
    assert initial.status == 200
    assert initial.json["clues"][0]["hints"] == [
        {
            "id": str(hints[0].id),
            "position": 1,
            "status": "available",
        },
        {"position": 2, "status": "locked"},
    ]
    assert initial.json["clues"][0]["can_reveal_answer"] is False
    assert "clock tower" not in initial.text
    assert "blue sign" not in initial.text

    _request, out_of_order = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/hints/{hints[1].id}/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert out_of_order.status == 400

    _request, first = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/hints/{hints[0].id}/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert first.status == 200
    assert first.json["created"] is True
    assert first.json["game"]["clues"][0]["hints"] == [
        {
            "id": str(hints[0].id),
            "position": 1,
            "status": "revealed",
            "text": "Look toward the clock tower.",
            "photo": None,
            "video": None,
        },
        {
            "id": str(hints[1].id),
            "position": 2,
            "status": "available",
        },
    ]
    assert "blue sign" not in first.text

    _request, duplicate = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/hints/{hints[0].id}/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate.status == 200
    assert duplicate.json["created"] is False

    _request, second = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/hints/{hints[1].id}/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert second.status == 200
    assert second.json["created"] is True
    assert second.json["game"]["clues"][0]["hints"][1]["text"] == ("Check beneath the blue sign.")
    assert second.json["game"]["clues"][0]["can_reveal_answer"] is False

    async with app.ctx.db.session() as db:
        reveals = list((await db.scalars(select(HintReveal))).all())
        assert {reveal.hint_id for reveal in reveals} == {hint.id for hint in hints}
        reveal_events = list(
            (await db.scalars(select(AuditEvent).where(AuditEvent.action == "hint.revealed"))).all()
        )
        assert len(reveal_events) == 2
        assert {event.actor_id for event in reveal_events} == {player.id}
        assert {event.entity_id for event in reveal_events} == {str(hint.id) for hint in hints}
        assert {event.after["position"] for event in reveal_events} == {1, 2}


async def test_answer_reveals_are_disabled_by_default(app, admin):
    player, _stranger, game = await make_game(app, admin)
    async with app.ctx.db.session() as db:
        clue = await db.scalar(select(Clue).where(Clue.game_id == game.id).order_by(Clue.position))

    cookies, headers = auth(app, player)
    _request, response = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clue.id}/answer/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )

    assert response.status == 403
    assert "Walk to the clock." not in response.text


async def test_player_can_reveal_answers_after_all_hints_and_still_needs_code(app, admin):
    player, _stranger, game = await make_game(app, admin)
    async with app.ctx.db.session() as db:
        stored_game = await db.get(Game, game.id)
        stored_game.allow_answer_reveal = True
        clues = list(
            (
                await db.scalars(
                    select(Clue).where(Clue.game_id == game.id).order_by(Clue.position)
                )
            ).all()
        )
        hints = [
            Hint(
                clue_id=clues[0].id,
                position=1,
                text="Look toward the clock tower.",
            ),
            Hint(
                clue_id=clues[0].id,
                position=2,
                text="Check beneath the blue sign.",
            ),
        ]
        db.add_all(hints)
        await db.flush()

    cookies, headers = auth(app, player)
    _request, initial = await app.asgi_client.get(
        f"/api/v1/player/games/{game.id}",
        cookies=cookies,
    )
    assert initial.status == 200
    assert initial.json["clues"][0]["can_reveal_answer"] is False
    assert initial.json["clues"][1]["can_reveal_answer"] is True

    _request, too_early = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/answer/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert too_early.status == 400
    assert clues[0].content not in too_early.text

    _request, no_hint_reveal = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/answer/reveal",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert no_hint_reveal.status == 200
    no_hint_clue = no_hint_reveal.json["game"]["clues"][1]
    assert no_hint_reveal.json["created"] is True
    assert no_hint_clue["status"] == "available"
    assert no_hint_clue["answer"] == "Find the mural."
    assert no_hint_clue["can_reveal_answer"] is False
    assert "MURAL-2" not in no_hint_reveal.text

    _request, wrong_code = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/complete",
        json={"code": "WRONG"},
        cookies=cookies,
        headers=headers,
    )
    assert wrong_code.status == 400

    for hint in hints:
        _request, hint_reveal = await app.asgi_client.post(
            f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/hints/{hint.id}/reveal",
            json={},
            cookies=cookies,
            headers=headers,
        )
        assert hint_reveal.status == 200
    assert hint_reveal.json["game"]["clues"][0]["can_reveal_answer"] is True

    answer_url = f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/answer/reveal"
    _request, revealed = await app.asgi_client.post(
        answer_url,
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert revealed.status == 200
    assert revealed.json["created"] is True
    revealed_clue = revealed.json["game"]["clues"][0]
    assert revealed_clue["status"] == "available"
    assert revealed_clue["answer"] == "Walk to the clock."
    assert revealed_clue["can_reveal_answer"] is False

    _request, duplicate = await app.asgi_client.post(
        answer_url,
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate.status == 200
    assert duplicate.json["created"] is False

    _request, completed = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/complete",
        json={"code": "CLOCK-1"},
        cookies=cookies,
        headers=headers,
    )
    assert completed.status == 200
    assert completed.json["created"] is True
    assert completed.json["game"]["clues"][0]["status"] == "completed"

    async with app.ctx.db.session() as db:
        answer_reveals = list(
            (
                await db.scalars(select(ClueAnswerReveal).order_by(ClueAnswerReveal.revealed_at))
            ).all()
        )
        assert {reveal.clue_id for reveal in answer_reveals} == {clue.id for clue in clues}
        answer_events = list(
            (
                await db.scalars(
                    select(AuditEvent).where(AuditEvent.action == "clue.answer_revealed")
                )
            ).all()
        )
        assert {event.entity_id for event in answer_events} == {str(clue.id) for clue in clues}
        assert {event.after["game_id"] for event in answer_events} == {str(game.id)}


async def test_player_can_complete_clues_in_any_order(app, admin):
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

    _request, second = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/complete",
        json={"code": " mural-2 "},
        cookies=cookies,
        headers=headers,
    )
    assert second.status == 200
    assert second.json["created"] is True
    assert second.json["game"]["clues"][0]["status"] == "available"
    assert second.json["game"]["clues"][1]["status"] == "completed"
    assert second.json["game"]["clues"][1]["answer"] == "Find the mural."
    assert second.json["game"]["complete"] is False

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
    assert first.json["game"]["clues"][1]["status"] == "completed"
    assert first.json["game"]["clues"][1]["clue"] == "Second Reveal"
    assert first.json["game"]["clues"][1]["answer"] == "Find the mural."
    assert first.json["game"]["complete"] is True
    assert first.json["game"]["closing_message"] == "Thanks for playing!"

    _request, duplicate = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[0].id}/complete",
        json={"code": "CLOCK-1"},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate.status == 200
    assert duplicate.json["created"] is False

    _request, duplicate_second = await app.asgi_client.post(
        f"/api/v1/player/games/{game.id}/clues/{clues[1].id}/complete",
        json={"code": "mural-2"},
        cookies=cookies,
        headers=headers,
    )
    assert duplicate_second.status == 200
    assert duplicate_second.json["created"] is False

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
