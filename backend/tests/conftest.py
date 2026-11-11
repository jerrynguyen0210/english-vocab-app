import os
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Test configuration never depends on developer credentials or a running database.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/test"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["CORS_ORIGINS"] = '["http://localhost:8081"]'

from app.core.config import Settings, get_settings

# Settings must never load a developer's .env (for example insecure HTTP cookies).
Settings.model_config["env_file"] = None
os.environ["APP_ENVIRONMENT"] = "test"
os.environ["AUTH_COOKIE_SECURE"] = "true"
get_settings.cache_clear()


@pytest.fixture
def api_database_url(tmp_path):
    """Use SQLite by default, or an isolated PostgreSQL schema when requested."""
    configured = os.environ.get("TEST_POSTGRES_URL")
    if not configured:
        yield f"sqlite:///{tmp_path}/api.db"
        return
    url = make_url(configured)
    if url.get_backend_name() != "postgresql":
        raise ValueError("TEST_POSTGRES_URL must refer to PostgreSQL")
    schema = "test_api_" + uuid.uuid4().hex
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        yield url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
