"""Add a customizable game closing message."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0003"
down_revision: str | Sequence[str] | None = "20260728_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("games", sa.Column("closing_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "closing_message")
