"""Add append-only review history with word ownership validation."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        op.create_index("uq_words_id_user", "words", ["id", "user_id"], unique=True)
    else:
        op.create_unique_constraint("uq_words_id_user", "words", ["id", "user_id"])
    op.create_table(
        "review_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("word_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("typed_answer", sa.Text(), nullable=False),
        sa.Column("normalised_answer", sa.Text(), nullable=False),
        sa.Column("result", sa.String(9), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("time_taken_ms", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["word_id", "user_id"],
            ["words.id", "words.user_id"],
            name="fk_review_attempts_word_owner",
        ),
        sa.CheckConstraint(
            "result IN ('correct', 'incorrect')", name="ck_review_attempts_result"
        ),
        sa.CheckConstraint(
            "time_taken_ms >= 0", name="ck_review_attempts_time_nonnegative"
        ),
    )
    for field in ("word", "user"):
        op.create_index(
            f"ix_review_attempts_{field}_reviewed",
            "review_attempts",
            [f"{field}_id", "reviewed_at"],
        )
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_review_attempt_change() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Review attempts are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER review_attempts_append_only
            BEFORE UPDATE OR DELETE OR TRUNCATE ON review_attempts
            FOR EACH STATEMENT EXECUTE FUNCTION reject_review_attempt_change()
        """)
    elif op.get_context().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER review_attempts_no_{action.lower()}
                BEFORE {action} ON review_attempts
                BEGIN SELECT RAISE(ABORT, 'Review attempts are append-only'); END
            """)


def downgrade() -> None:
    op.drop_table("review_attempts")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_review_attempt_change()")
    if op.get_context().dialect.name == "sqlite":
        op.drop_index("uq_words_id_user", table_name="words")
    else:
        op.drop_constraint("uq_words_id_user", "words", type_="unique")
