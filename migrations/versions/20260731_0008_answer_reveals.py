"""Add configurable per-player clue answer reveals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0008"
down_revision: str | Sequence[str] | None = "20260731_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column(
            "allow_answer_reveal",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "clue_answer_reveals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_player_id", sa.Uuid(), nullable=False),
        sa.Column("clue_id", sa.Uuid(), nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_player_id"], ["game_players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clue_id"], ["clues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_player_id",
            "clue_id",
            name="uq_clue_answer_reveals_membership_clue",
        ),
    )
    op.create_index(
        "ix_clue_answer_reveals_game_player_id",
        "clue_answer_reveals",
        ["game_player_id"],
    )
    op.create_index(
        "ix_clue_answer_reveals_clue_id",
        "clue_answer_reveals",
        ["clue_id"],
    )
    op.create_index(
        "ix_clue_answer_reveals_membership_time",
        "clue_answer_reveals",
        ["game_player_id", "revealed_at"],
    )


def downgrade() -> None:
    op.drop_table("clue_answer_reveals")
    op.drop_column("games", "allow_answer_reveal")
