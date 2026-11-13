"""Persist per-user Common questions and durable LLM generation jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "common_word_questions",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("normalised_word", sa.Text(), nullable=False),
        sa.Column("part_of_speech", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id", "normalised_word", name="uq_common_words_user_word"
        ),
        sa.CheckConstraint(
            "correct_index BETWEEN 0 AND 3", name="ck_common_words_answer"
        ),
    )
    op.create_index(
        "ix_common_words_user_presented",
        "common_word_questions",
        ["user_id", "last_presented_at"],
    )
    op.create_table(
        "common_word_jobs",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_category", sa.String(32), nullable=True),
    )
    op.create_index(
        "ix_common_word_jobs_available", "common_word_jobs", ["available_at"]
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
