"""Remove the retired Common word bank and generation queue.

Applying this revision permanently deletes existing Common questions, learned
answers, and queued refills. Saved vocabulary and review history are retained.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("common_word_jobs")
    op.drop_table("common_word_questions")


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
