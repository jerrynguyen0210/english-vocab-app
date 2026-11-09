"""Persist authentication sessions and shared rate limits."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("native", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "auth_rate_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auth_rate_buckets_expires_at", "auth_rate_buckets", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("auth_rate_buckets")
    op.drop_table("auth_sessions")
