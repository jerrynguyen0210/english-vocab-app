import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import User


def test_user_identity_and_defaults():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        password_user = User(email="local@example.test", password_hash="test-hash")
        provider_user = User(
            email="provider@example.test", auth_provider_id="issuer:subject"
        )
        session.add_all([password_user, provider_user])
        session.commit()
        assert password_user.id != provider_user.id
        assert password_user.created_at is not None
        assert password_user.disabled_at is None
        assert password_user.deleted_at is None
    engine.dispose()


@pytest.mark.parametrize(
    "values",
    [
        {"email": "missing@example.test"},
        {"email": "blank@example.test", "password_hash": " "},
        {"email": "", "password_hash": "test-hash"},
        {"email": "blank@example.test", "auth_provider_id": " "},
        {"email": "existing@example.test", "password_hash": "test-hash"},
        {"email": "other@example.test", "auth_provider_id": "issuer:existing"},
    ],
)
def test_invalid_or_duplicate_identity_is_rejected(values):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(email="existing@example.test", auth_provider_id="issuer:existing")
        )
        session.commit()
        session.add(User(**values))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()
