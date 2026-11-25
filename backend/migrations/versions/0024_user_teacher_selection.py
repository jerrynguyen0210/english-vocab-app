"""Persist each user's selected teacher."""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("selected_teacher_id", sa.String(128), nullable=True)
    )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
