import os
import secrets

# Test configuration never depends on developer credentials or a running database.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/test"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["CORS_ORIGINS"] = '["http://localhost:8081"]'
