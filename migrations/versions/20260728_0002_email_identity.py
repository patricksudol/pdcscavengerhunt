"""Replace username and display name with email address and full name."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0002"
down_revision: str | Sequence[str] | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_normalized_username", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "username",
            new_column_name="email_address",
            existing_type=sa.String(80),
            type_=sa.String(320),
            existing_nullable=False,
        )
        batch.alter_column(
            "normalized_username",
            new_column_name="normalized_email_address",
            existing_type=sa.String(80),
            type_=sa.String(320),
            existing_nullable=False,
        )
        batch.alter_column(
            "display_name",
            new_column_name="full_name",
            existing_type=sa.String(180),
            existing_nullable=False,
        )
    op.execute(
        """
        UPDATE users
        SET email_address = CASE
            WHEN email_address LIKE '%@%' THEN LOWER(email_address)
            WHEN LOWER(email_address) = 'admin' THEN 'admin@pdc.test'
            ELSE LOWER(email_address) || '@local.invalid'
        END
        """
    )
    op.execute("UPDATE users SET normalized_email_address = email_address")
    op.create_index(
        "ix_users_normalized_email_address",
        "users",
        ["normalized_email_address"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_normalized_email_address", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email_address",
            new_column_name="username",
            existing_type=sa.String(320),
            type_=sa.String(80),
            existing_nullable=False,
        )
        batch.alter_column(
            "normalized_email_address",
            new_column_name="normalized_username",
            existing_type=sa.String(320),
            type_=sa.String(80),
            existing_nullable=False,
        )
        batch.alter_column(
            "full_name",
            new_column_name="display_name",
            existing_type=sa.String(180),
            existing_nullable=False,
        )
    op.create_index(
        "ix_users_normalized_username",
        "users",
        ["normalized_username"],
        unique=True,
    )
