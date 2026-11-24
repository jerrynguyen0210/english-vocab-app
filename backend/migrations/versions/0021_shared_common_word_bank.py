"""Shared 1,000-word bank, per-user progress and server-graded practice."""

import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bank = op.create_table(
        "common_words",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("normalised_word", sa.Text(), nullable=False, unique=True),
        sa.Column("ipa", sa.String(120)),
        sa.Column("part_of_speech", sa.String(32), nullable=False),
        sa.Column("english_explanation", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("length(trim(word)) > 0", name="ck_common_bank_word"),
        sa.CheckConstraint(
            "length(trim(normalised_word)) > 0", name="ck_common_bank_normalised"
        ),
        sa.CheckConstraint(
            "length(trim(english_explanation)) > 0", name="ck_common_bank_meaning"
        ),
    )
    op.create_table(
        "user_common_word_progress",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "common_word_id",
            sa.Uuid(),
            sa.ForeignKey("common_words.id"),
            primary_key=True,
        ),
        sa.Column("last_presented_at", sa.DateTime(timezone=True)),
        sa.Column("learned_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "common_practice_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "common_word_id",
            sa.Uuid(),
            sa.ForeignKey("common_words.id"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("selected_index", sa.Integer()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "correct_index BETWEEN 0 AND 3", name="ck_common_practice_correct"
        ),
        sa.CheckConstraint(
            "selected_index IS NULL OR selected_index BETWEEN 0 AND 3",
            name="ck_common_practice_selected",
        ),
        sa.CheckConstraint(
            "(selected_index IS NULL AND answered_at IS NULL) OR (selected_index IS NOT NULL AND answered_at IS NOT NULL)",
            name="ck_common_practice_answer_pair",
        ),
    )
    op.create_index("ix_common_practice_user", "common_practice_questions", ["user_id"])
    # Frozen revision-specific content: migrations never need WordNet or network access.
    entries = json.loads(
        (
            Path(__file__).resolve().parents[1] / "data" / "0021_common_words.json"
        ).read_text()
    )
    if len(entries) != 1000 or len({row["normalised_word"] for row in entries}) != 1000:
        raise RuntimeError("Common bank seed must contain 1,000 unique entries")
    for row in entries:
        row["id"] = UUID(row["id"])
    op.bulk_insert(bank, entries)


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
