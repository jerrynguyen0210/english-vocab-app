"""Remove user-entered topic tags; backend topic search is deferred."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("word_topics")


def downgrade() -> None:
    raise RuntimeError("Deployment migrations are forward-only")
