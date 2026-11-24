"""Durable, account-owned Common practice generation batches."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "common_practice_batches",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("question_ids", sa.JSON(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'complete', 'failed')",
            name="ck_common_batch_status",
        ),
    )
    op.create_index(
        "ix_common_practice_batches_available_at",
        "common_practice_batches",
        ["available_at"],
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
