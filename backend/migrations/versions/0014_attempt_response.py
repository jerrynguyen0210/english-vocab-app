"""Retain the scheduling response for newly accepted review attempts."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical results cannot be reconstructed reliably. Do not rewrite
    # append-only history or substitute the current schedule for an old result.
    op.add_column(
        "review_attempts",
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
