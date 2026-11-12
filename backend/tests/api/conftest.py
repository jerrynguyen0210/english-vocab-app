"""Shared migrated database and authenticated API client."""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.main import app


@pytest.fixture
def api(api_database_url, monkeypatch):
    # API contract tests stay offline; dedicated tests assert persistence/failures.
    monkeypatch.setattr(
        "app.services.prompt_jobs.worker.generate_review",
        lambda word, meaning, **kwargs: {
            "prompt_sentence": "A saved _____ prompt.",
            "answer": word,
        },
    )
    url = api_database_url
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    sqlite = url.startswith("sqlite:")
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if sqlite else {}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        if sqlite:
            connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app, base_url="https://testserver") as client:

            def account(email):
                tokens = client.post(
                    "/api/v1/auth/register",
                    headers={"X-Auth-Platform": "native"},
                    json={"email": email, "password": "long test password"},
                ).json()
                return {"Authorization": "Bearer " + tokens["access_token"]}, tokens

            owner, tokens = account("owner@example.com")
            other, _ = account("other@example.com")
            yield client, db, owner, other, tokens
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()
