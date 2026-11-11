"""Add saved topic tags and SM-2 state without changing existing due dates."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "word_topics",
        sa.Column(
            "word_id",
            sa.Uuid(),
            sa.ForeignKey("words.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag", sa.String(100), primary_key=True),
    )
    op.create_index("ix_word_topics_tag", "word_topics", ["tag"])
    with op.batch_alter_table("review_states") as batch:
        batch.add_column(
            sa.Column("repetitions", sa.Integer(), server_default="0", nullable=False)
        )
        batch.add_column(
            sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False)
        )
        batch.add_column(
            sa.Column("ease_factor", sa.Float(), server_default="2.5", nullable=False)
        )
        batch.create_check_constraint("ck_review_repetitions", "repetitions >= 0")
        batch.create_check_constraint("ck_review_interval", "interval_days >= 0")
        batch.create_check_constraint("ck_review_ease", "ease_factor >= 1.3")


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
