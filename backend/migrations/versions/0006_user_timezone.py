"""Store each user's IANA timezone; existing users default to UTC."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone", sa.String(255), server_default=sa.text("'UTC'"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
