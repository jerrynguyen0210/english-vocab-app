"""Queue new-word prompt generation independently of HTTP requests."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_jobs",
        sa.Column(
            "word_id",
            sa.Uuid(),
            sa.ForeignKey("words.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_prompt_jobs_available_at", "prompt_jobs", ["available_at"])


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
