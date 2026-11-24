"""Retire the bundled vocabulary; operators populate the shared bank using the LLM.

Deletes the 0021 seed rows and their Common learning/questions. Independently
saved recall words and operator-generated bank entries are retained.
"""

import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    entries = json.loads(
        (
            Path(__file__).resolve().parents[1] / "data" / "0021_common_words.json"
        ).read_text()
    )
    # Keep each IN clause below SQLite's older bind-parameter limit.
    for offset in range(0, len(entries), 100):
        ids = [UUID(entry["id"]) for entry in entries[offset : offset + 100]]
        for name, column in [
            ("common_practice_questions", "common_word_id"),
            ("user_common_word_progress", "common_word_id"),
            ("common_words", "id"),
        ]:
            table = sa.table(name, sa.column(column, sa.Uuid()))
            op.execute(table.delete().where(table.c[column].in_(ids)))


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
