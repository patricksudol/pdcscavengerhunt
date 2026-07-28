import asyncio

from sqlalchemy import select

from .db import Database
from .models import User
from .security import hash_password, normalize_username
from .settings import get_settings


async def seed_admin() -> None:
    settings = get_settings()
    if not settings.seed_admin_username or not settings.seed_admin_password:
        return
    database = Database(settings.database_url)
    try:
        normalized = normalize_username(settings.seed_admin_username)
        async with database.session() as db:
            existing = await db.scalar(
                select(User).where(User.normalized_username == normalized)
            )
            if existing:
                return
            db.add(
                User(
                    username=settings.seed_admin_username,
                    normalized_username=normalized,
                    display_name=settings.seed_admin_name,
                    password_hash=hash_password(settings.seed_admin_password),
                    is_admin=True,
                )
            )
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed_admin())
