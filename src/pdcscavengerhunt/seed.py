import asyncio

from sqlalchemy import select

from .db import Database
from .models import AuditEvent, User
from .security import hash_password, normalize_email_address
from .settings import get_settings


async def seed_admin() -> None:
    settings = get_settings()
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return
    database = Database(settings.database_url)
    try:
        normalized = normalize_email_address(settings.seed_admin_email)
        async with database.session() as db:
            existing = await db.scalar(
                select(User).where(User.normalized_email_address == normalized)
            )
            if existing:
                return
            user = User(
                email_address=settings.seed_admin_email,
                normalized_email_address=normalized,
                full_name=settings.seed_admin_name,
                password_hash=hash_password(settings.seed_admin_password),
                is_admin=True,
            )
            db.add(user)
            await db.flush()
            db.add(
                AuditEvent(
                    action="user.seeded",
                    entity_type="user",
                    entity_id=str(user.id),
                    after={
                        "email_address": user.email_address,
                        "full_name": user.full_name,
                        "is_admin": True,
                        "active": True,
                        "password_set": True,
                    },
                )
            )
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed_admin())
