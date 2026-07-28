from __future__ import annotations

from sqlalchemy import select

from pdcscavengerhunt.models import AuditEvent, PasswordSetupToken, User
from pdcscavengerhunt.security import verify_password

from .conftest import auth


async def test_admin_can_invite_player_and_invite_is_single_use(app, admin):
    cookies, headers = auth(app, admin)
    _request, created = await app.asgi_client.post(
        "/api/v1/admin/users",
        json={
            "email_address": "player.one@example.com",
            "full_name": "Player One",
            "is_admin": False,
        },
        cookies=cookies,
        headers=headers,
    )
    assert created.status == 201
    assert created.json["password_set"] is False
    token = created.json["setup_url"].rsplit("/", 1)[-1]

    _request, details = await app.asgi_client.get(
        f"/api/v1/auth/password-setup/{token}"
    )
    assert details.status == 200
    assert details.json["email_address"] == "player.one@example.com"

    _request, completed = await app.asgi_client.post(
        f"/api/v1/auth/password-setup/{token}",
        json={"password": "strong-player-password"},
    )
    assert completed.status == 200

    _request, reused = await app.asgi_client.post(
        f"/api/v1/auth/password-setup/{token}",
        json={"password": "another-strong-password"},
    )
    assert reused.status == 400

    async with app.ctx.db.session() as db:
        player = await db.scalar(
            select(User).where(
                User.normalized_email_address == "player.one@example.com"
            )
        )
        assert player
        assert verify_password("strong-player-password", player.password_hash)


async def test_player_can_login_and_admin_api_is_forbidden(app, admin):
    async with app.ctx.db.session() as db:
        player = User(
            email_address="hunter@example.com",
            normalized_email_address="hunter@example.com",
            full_name="Hunter",
            password_hash=admin.password_hash,
        )
        db.add(player)

    _request, login = await app.asgi_client.post(
        "/api/v1/auth/login",
        json={
            "email_address": "HUNTER@EXAMPLE.COM",
            "password": "test-admin-password",
        },
    )
    assert login.status == 200
    assert login.json["user"]["is_admin"] is False

    _request, forbidden = await app.asgi_client.get(
        "/api/v1/admin/dashboard",
        cookies={"pdc_hunt_session": login.cookies["pdc_hunt_session"]},
    )
    assert forbidden.status == 403


async def test_logout_is_audited(app, admin):
    cookies, headers = auth(app, admin)
    _request, response = await app.asgi_client.post(
        "/api/v1/auth/logout",
        cookies=cookies,
        headers=headers,
    )

    assert response.status == 200
    assert response.json == {"signed_out": True}
    async with app.ctx.db.session() as db:
        event = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "auth.logout")
        )
        assert event
        assert event.actor_id == admin.id
        assert event.entity_type == "user"
        assert event.entity_id == str(admin.id)
        assert event.request_id


async def test_mutations_require_csrf(app, admin):
    cookies, _headers = auth(app, admin)
    _request, response = await app.asgi_client.post(
        "/api/v1/admin/games",
        json={"title": "No CSRF"},
        cookies=cookies,
    )
    assert response.status == 403


async def test_regenerating_setup_link_invalidates_previous_link(app, admin):
    cookies, headers = auth(app, admin)
    _request, created = await app.asgi_client.post(
        "/api/v1/admin/users",
        json={
            "email_address": "invitee@example.com",
            "full_name": "Invitee",
        },
        cookies=cookies,
        headers=headers,
    )
    first_token = created.json["setup_url"].rsplit("/", 1)[-1]
    _request, regenerated = await app.asgi_client.post(
        f"/api/v1/admin/users/{created.json['id']}/setup-link",
        cookies=cookies,
        headers=headers,
    )
    second_token = regenerated.json["setup_url"].rsplit("/", 1)[-1]
    assert first_token != second_token

    _request, old = await app.asgi_client.get(
        f"/api/v1/auth/password-setup/{first_token}"
    )
    _request, new = await app.asgi_client.get(
        f"/api/v1/auth/password-setup/{second_token}"
    )
    assert old.status == 400
    assert new.status == 200

    async with app.ctx.db.session() as db:
        tokens = list((await db.scalars(select(PasswordSetupToken))).all())
        assert len(tokens) == 2
        assert sum(token.used_at is None for token in tokens) == 1
