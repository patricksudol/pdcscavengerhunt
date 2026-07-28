from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import create_engine

from pdcscavengerhunt.app import create_app
from pdcscavengerhunt.models import Base, User
from pdcscavengerhunt.security import hash_password, issue_session
from pdcscavengerhunt.settings import Settings


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.db"
    sync_engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        public_base_url="http://localhost:8000",
        session_secret="test-session-secret-that-is-long-enough",
        clue_code_secret="test-clue-secret-that-is-also-long-enough",
        secure_cookies=False,
    )
    app = create_app(settings, name=f"PDCScavengerHuntTest-{id(tmp_path)}")
    yield app


@pytest_asyncio.fixture
async def admin(app):
    user = User(
        email_address="admin@example.com",
        normalized_email_address="admin@example.com",
        full_name="Admin User",
        password_hash=hash_password("test-admin-password"),
        is_admin=True,
        last_login_at=datetime.now(UTC),
    )
    async with app.ctx.db.session() as db:
        db.add(user)
        await db.flush()
    return user


def auth(app, user):
    csrf_token = "test-csrf-token"
    return (
        {"pdc_hunt_session": issue_session(user, app.ctx.settings, csrf_token)},
        {"X-CSRF-Token": csrf_token},
    )
