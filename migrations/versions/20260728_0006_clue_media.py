"""Add one photo and one video attachment per clue."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0006"
down_revision: str | Sequence[str] | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clue_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clue_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(length=5), nullable=False),
        sa.Column("provider_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ready",
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clue_id"], ["clues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clue_id", "media_type", name="uq_clue_media_clue_type"),
        sa.UniqueConstraint("provider_key"),
    )
    op.create_index("ix_clue_media_clue_id", "clue_media", ["clue_id"])
    op.create_index("ix_clue_media_media_type", "clue_media", ["media_type"])
    op.create_index("ix_clue_media_status", "clue_media", ["status"])


def downgrade() -> None:
    op.drop_table("clue_media")
