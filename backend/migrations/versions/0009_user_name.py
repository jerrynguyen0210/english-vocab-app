"""Store optional names for existing and new accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(100), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only.")
