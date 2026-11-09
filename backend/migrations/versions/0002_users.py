"""Add user identity and account lifecycle."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=True),
        sa.Column("auth_provider_id", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("auth_provider_id"),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR auth_provider_id IS NOT NULL",
            name="ck_users_auth_identity",
        ),
        sa.CheckConstraint("length(trim(email)) > 0", name="ck_users_email_nonempty"),
        sa.CheckConstraint(
            "password_hash IS NULL OR length(trim(password_hash)) > 0",
            name="ck_users_password_hash_nonempty",
        ),
        sa.CheckConstraint(
            "auth_provider_id IS NULL OR length(trim(auth_provider_id)) > 0",
            name="ck_users_auth_provider_id_nonempty",
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
