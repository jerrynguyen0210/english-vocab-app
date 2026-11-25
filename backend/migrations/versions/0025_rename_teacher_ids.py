"""Rename catalog IDs while preserving existing user preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    users = sa.table("users", sa.column("selected_teacher_id", sa.String(128)))
    for old_id, new_id in (
        ("suggested-name-01", "teacher-01"),
        ("suggested-name-02", "teacher-02"),
    ):
        op.execute(
            users.update()
            .where(users.c.selected_teacher_id == old_id)
            .values(selected_teacher_id=new_id)
        )


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
