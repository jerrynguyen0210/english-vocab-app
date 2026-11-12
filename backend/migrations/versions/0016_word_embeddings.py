"""Persist word embeddings without changing vocabulary or review history."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("words", sa.Column("embedding_vector", sa.JSON(), nullable=True))
    op.add_column("words", sa.Column("embedding_model", sa.Text(), nullable=True))
    op.add_column("words", sa.Column("embedding_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
