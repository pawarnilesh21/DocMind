import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

# Never load the user's configured database or make real provider calls in automated tests.
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-not-for-production-123456789"
os.environ["DEBUG"] = "false"
os.environ["COOKIE_SECURE"] = "false"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["ALLOWED_HOSTS"] = '["testserver","localhost","127.0.0.1"]'
os.environ["ALLOWED_ORIGINS"] = '["http://localhost:5173"]'
integration_url = os.environ.get("TEST_DATABASE_URL", "")
if integration_url and (
    urlparse(integration_url).path != "/docmind_test"
    or urlparse(integration_url).hostname not in {"localhost", "127.0.0.1", "db"}
):
    raise RuntimeError("TEST_DATABASE_URL must target the isolated local docmind_test database")
db_path = Path(tempfile.gettempdir()) / f"docmind-{uuid.uuid4().hex}.test.db"
os.environ["DATABASE_URL"] = integration_url or f"sqlite:///{db_path.as_posix()}"

import pytest
from fastapi.testclient import TestClient

from app.core.security import password_hasher
from app.db.database import Base, SessionLocal, engine
from app.db.models import User
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def schema():
    if integration_url:
        from alembic.config import Config

        from alembic import command

        command.upgrade(Config("alembic.ini"), "head")
    else:
        Base.metadata.create_all(engine)
    yield
    engine.dispose()
    if not integration_url:
        db_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_database(schema, monkeypatch):
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())

    def forbidden(*args, **kwargs):
        raise AssertionError("Real provider calls are forbidden in the test suite")

    monkeypatch.setattr("app.services.provider.post_json", forbidden)
    monkeypatch.setattr("app.services.embedding_service.post_json", forbidden)
    monkeypatch.setattr("app.services.llm_service.post_json", forbidden)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as client:
        client.headers["X-Requested-With"] = "DocMind"
        yield client


@pytest.fixture
def users(db):
    values = [
        User(email=f"user{i}@example.com", password_hash=password_hasher.hash("long-test-password"))
        for i in (1, 2)
    ]
    db.add_all(values)
    db.commit()
    return values


@pytest.fixture
def signed_in(client, users):
    response = client.post(
        "/api/auth/login", json={"email": users[0].email, "password": "long-test-password"}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client
