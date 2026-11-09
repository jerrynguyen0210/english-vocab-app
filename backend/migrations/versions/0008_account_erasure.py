"""Allow review-history erasure only for accounts marked for deletion."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TRIGGER review_attempts_append_only ON review_attempts")
        op.execute("""
            CREATE FUNCTION allow_deleted_account_erasure() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF EXISTS (SELECT 1 FROM users WHERE id = OLD.user_id AND deleted_at IS NOT NULL) THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'Review attempts are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER review_attempts_append_only
            BEFORE UPDATE OR TRUNCATE ON review_attempts FOR EACH STATEMENT
            EXECUTE FUNCTION reject_review_attempt_change()
        """)
        op.execute("""
            CREATE TRIGGER review_attempts_account_erasure BEFORE DELETE ON review_attempts
            FOR EACH ROW EXECUTE FUNCTION allow_deleted_account_erasure()
        """)
    elif op.get_context().dialect.name == "sqlite":
        op.execute("DROP TRIGGER review_attempts_no_delete")
        op.execute("""
            CREATE TRIGGER review_attempts_no_delete BEFORE DELETE ON review_attempts
            WHEN NOT EXISTS (SELECT 1 FROM users WHERE id = OLD.user_id AND deleted_at IS NOT NULL)
            BEGIN SELECT RAISE(ABORT, 'Review attempts are append-only'); END
        """)


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TRIGGER review_attempts_account_erasure ON review_attempts")
        op.execute("DROP FUNCTION allow_deleted_account_erasure()")
        op.execute("DROP TRIGGER review_attempts_append_only ON review_attempts")
        op.execute("""
            CREATE TRIGGER review_attempts_append_only
            BEFORE UPDATE OR DELETE OR TRUNCATE ON review_attempts FOR EACH STATEMENT
            EXECUTE FUNCTION reject_review_attempt_change()
        """)
    elif op.get_context().dialect.name == "sqlite":
        op.execute("DROP TRIGGER review_attempts_no_delete")
        op.execute("""
            CREATE TRIGGER review_attempts_no_delete BEFORE DELETE ON review_attempts
            BEGIN SELECT RAISE(ABORT, 'Review attempts are append-only'); END
        """)
