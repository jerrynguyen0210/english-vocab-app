"""Retain failed generation jobs for inspection and explicit retry."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_jobs", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Store categories only; provider messages may contain private vocabulary.
    op.add_column(
        "prompt_jobs", sa.Column("failure_category", sa.String(32), nullable=True)
    )
    # Retained terminal failures must not accumulate in the worker's ready index.
    op.drop_index("ix_prompt_jobs_available_at", table_name="prompt_jobs")
    op.create_index(
        "ix_prompt_jobs_pending_available_at",
        "prompt_jobs",
        ["available_at", "word_id"],
        postgresql_where=sa.text("failed_at IS NULL"),
        sqlite_where=sa.text("failed_at IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
