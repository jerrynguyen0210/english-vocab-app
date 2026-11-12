import secrets

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_settings_read_environment(monkeypatch):
    key = secrets.token_urlsafe(48)
    monkeypatch.setenv("SECRET_KEY", key)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@db/test")
    monkeypatch.setenv("CORS_ORIGINS", '["https://preview.example.com"]')
    router_key = secrets.token_urlsafe(32)
    monkeypatch.setenv("OPENROUTER_API_KEY", router_key)
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "45")
    settings = Settings(_env_file=None)
    assert settings.openrouter_api_key.get_secret_value() == router_key
    assert router_key not in repr(settings)
    assert settings.openrouter_model == "test/model"
    assert settings.openrouter_timeout_seconds == 45
    assert settings.secret_key.get_secret_value() == key
    assert key not in repr(settings)
    assert settings.database_url.endswith("@db/test")
    assert settings.cors_origins == ["https://preview.example.com"]


def test_cors_allows_configured_origin_only():
    with TestClient(app) as client:
        for origin, expected_status in [
            ("http://localhost:8081", 200),
            ("https://untrusted.example.com", 400),
        ]:
            response = client.options("/health", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            })
            assert response.status_code == expected_status
            assert response.headers.get("access-control-allow-origin") == (
                origin if expected_status == 200 else None
            )
