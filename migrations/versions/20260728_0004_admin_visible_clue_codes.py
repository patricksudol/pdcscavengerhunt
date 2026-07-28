"""Store clue codes for display in admin-only views."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | Sequence[str] | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clues", sa.Column("code", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("clues", "code")
