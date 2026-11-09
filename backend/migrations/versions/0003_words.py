"""Add user-owned vocabulary words."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("normalised_word", sa.Text(), nullable=False),
        sa.Column("english_explanation", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "user_id", "normalised_word", name="uq_words_user_normalised"
        ),
        sa.CheckConstraint("length(trim(word)) > 0", name="ck_words_word_nonempty"),
        sa.CheckConstraint(
            "length(trim(normalised_word)) > 0", name="ck_words_normalised_nonempty"
        ),
        sa.CheckConstraint(
            "length(trim(english_explanation)) > 0",
            name="ck_words_explanation_nonempty",
        ),
    )


def downgrade() -> None:
    op.drop_table("words")
