"""Store IPA pronunciations for Common questions."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "common_word_questions", sa.Column("ipa", sa.String(120), nullable=True)
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
