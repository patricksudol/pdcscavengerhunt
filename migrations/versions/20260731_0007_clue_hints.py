"""Add ordered clue hints with per-player reveal state and media."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0007"
down_revision: str | Sequence[str] | None = "20260728_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clue_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clue_id"], ["clues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clue_id", "position", name="uq_hints_clue_position"),
    )
    op.create_index("ix_hints_clue_id", "hints", ["clue_id"])
    op.create_index("ix_hints_clue_position", "hints", ["clue_id", "position"])

    op.create_table(
        "hint_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hint_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(length=5), nullable=False),
        sa.Column("provider_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="ready", nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hint_id"], ["hints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hint_id", "media_type", name="uq_hint_media_hint_type"),
        sa.UniqueConstraint("provider_key"),
    )
    op.create_index("ix_hint_media_hint_id", "hint_media", ["hint_id"])
    op.create_index("ix_hint_media_media_type", "hint_media", ["media_type"])
    op.create_index("ix_hint_media_status", "hint_media", ["status"])

    op.create_table(
        "hint_reveals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_player_id", sa.Uuid(), nullable=False),
        sa.Column("hint_id", sa.Uuid(), nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_player_id"], ["game_players.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["hint_id"], ["hints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_player_id", "hint_id", name="uq_hint_reveals_membership_hint"
        ),
    )
    op.create_index(
        "ix_hint_reveals_game_player_id", "hint_reveals", ["game_player_id"]
    )
    op.create_index("ix_hint_reveals_hint_id", "hint_reveals", ["hint_id"])
    op.create_index(
        "ix_hint_reveals_membership_time",
        "hint_reveals",
        ["game_player_id", "revealed_at"],
    )


def downgrade() -> None:
    op.drop_table("hint_reveals")
    op.drop_table("hint_media")
    op.drop_table("hints")
