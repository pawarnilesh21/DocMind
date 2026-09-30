"""Verify the isolated Docker review stack. This never targets a production database."""
import os
import time
import uuid
from urllib.parse import urlparse

os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["COOKIE_SECURE"] = "false"
os.environ["DATABASE_URL"] = "postgresql://docmind_test:local-test-only@127.0.0.1:55432/docmind_test"

import httpx
from sqlalchemy import select
from app.core.security import password_hasher
from app.db.database import SessionLocal
from app.db.models import User

BASE_URL = "http://127.0.0.1:18080"


def main():
    assert urlparse(os.environ["DATABASE_URL"]).path == "/docmind_test"
    email = f"smoke-{uuid.uuid4().hex}@example.com"
    password = uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(User(email=email, password_hash=password_hasher.hash(password)))
        db.commit()
    with httpx.Client(base_url=BASE_URL, timeout=20, headers={"X-Requested-With": "DocMind"}, trust_env=False) as client:
        home = client.get("/")
        assert home.status_code == 200 and "DocMind" in home.text
        assert "default-src 'self'" in home.headers["content-security-policy"]
        assert client.get("/ready").status_code == 200
        assert client.get("/api/documents/").status_code == 401
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        conv = client.post("/api/chat/", json={}).json()["id"]
        answer = client.post(f"/api/chat/{conv}/message", json={"content": "What do my documents say?", "request_id": str(uuid.uuid4())})
        assert answer.status_code == 200, answer.text
        assert answer.json()["metadata_"]["grounding"] == "abstained"
        # Valid UTF-8 but no extractable text: exercises the real subprocess parser,
        # permanent failure handling, and worker state updates without a paid API call.
        upload = client.post("/api/documents/upload", files={"file": ("blank.txt", b"   \n", "text/plain")})
        assert upload.status_code == 202, upload.text
        doc_id = upload.json()["id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = client.get(f"/api/documents/{doc_id}").json()["status"]
            if status == "failed":
                break
            time.sleep(0.5)
        assert status == "failed", status
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
        assert client.delete(f"/api/chat/{conv}").status_code == 204
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/chat/").status_code == 401
    with SessionLocal() as db:
        db.delete(db.scalar(select(User).where(User.email == email)))
        db.commit()
    print("Docker smoke passed: static app, CSP, readiness, auth, CSRF, Q&A abstention, worker subprocess, deletion, logout.")


if __name__ == "__main__":
    main()
