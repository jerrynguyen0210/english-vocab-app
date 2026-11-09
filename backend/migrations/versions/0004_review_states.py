"""Add one current review state per word."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_states",
        sa.Column("word_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "correct_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "incorrect_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("word_id"),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.CheckConstraint("level >= 0", name="ck_review_states_level_nonnegative"),
        sa.CheckConstraint(
            "correct_count >= 0", name="ck_review_states_correct_nonnegative"
        ),
        sa.CheckConstraint(
            "incorrect_count >= 0", name="ck_review_states_incorrect_nonnegative"
        ),
    )
    op.create_index("ix_review_states_due_at", "review_states", ["due_at"])
    # Existing words start at the same defaults as newly created states.
    op.execute(sa.text("INSERT INTO review_states (word_id) SELECT id FROM words"))


def downgrade() -> None:
    op.drop_index("ix_review_states_due_at", table_name="review_states")
    op.drop_table("review_states")
