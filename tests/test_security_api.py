import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.rate_limit import enforce_limit
from app.db.models import AuthSession, Conversation, Document, DocumentChunk, utcnow


def test_anonymous_cannot_list_or_upload(client):
    assert client.get("/api/documents/").status_code == 401
    assert client.get("/api/chat/").status_code == 401
    assert (
        client.post(
            "/api/documents/upload", files={"file": ("x.txt", b"private text", "text/plain")}
        ).status_code
        == 401
    )


def test_login_cookie_csrf_and_logout(signed_in):
    me = signed_in.get("/api/auth/me")
    assert me.status_code == 200
    cookie = signed_in.cookies.get("docmind_session")
    assert cookie
    csrf = signed_in.headers.pop("X-CSRF-Token")
    assert signed_in.post("/api/chat/", json={}).status_code == 403
    signed_in.headers["X-CSRF-Token"] = csrf
    assert signed_in.post("/api/chat/", json={}).status_code == 201
    response = signed_in.post("/api/auth/logout")
    assert response.status_code == 204
    assert signed_in.get("/api/chat/").status_code == 401


def test_login_sets_httponly_and_strict_cookie(client, users):
    response = client.post(
        "/api/auth/login", json={"email": users[0].email, "password": "long-test-password"}
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie


def test_origin_and_custom_header_required(client, users):
    body = {"email": users[0].email, "password": "long-test-password"}
    assert (
        client.post("/api/auth/login", json=body, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    client.headers.pop("X-Requested-With")
    assert client.post("/api/auth/login", json=body).status_code == 403


def test_session_expiry(signed_in, db):
    session = db.scalar(select(AuthSession))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert signed_in.get("/api/chat/").status_code == 401


def test_owner_isolation(signed_in, users, db):
    other_doc = Document(
        owner_id=users[1].id, filename="secret.txt", file_type="txt", file_size=6, status="ready"
    )
    other_conv = Conversation(owner_id=users[1].id, title="private")
    db.add_all([other_doc, other_conv])
    db.commit()
    assert signed_in.get("/api/documents/").json()["documents"] == []
    for suffix in ("", "/chunks"):
        assert signed_in.get(f"/api/documents/{other_doc.id}{suffix}").status_code == 404
    assert signed_in.delete(f"/api/documents/{other_doc.id}").status_code == 404
    assert signed_in.post(f"/api/documents/{other_doc.id}/retry").status_code == 404
    assert signed_in.get(f"/api/chat/{other_conv.id}/history").status_code == 404
    assert signed_in.delete(f"/api/chat/{other_conv.id}").status_code == 404
    assert (
        signed_in.post(
            f"/api/chat/{other_conv.id}/message", json={"content": "secret?", "request_id": str(uuid.uuid4())}
        ).status_code
        == 404
    )


def test_upload_is_durable_and_delete_cascades(signed_in, users, db):
    response = signed_in.post(
        "/api/documents/upload", files={"file": ("sample.txt", b"content for indexing", "text/plain")}
    )
    assert response.status_code == 202
    doc = db.get(Document, uuid.UUID(response.json()["id"]))
    assert (
        doc.status == "queued" and doc.source_bytes == b"content for indexing" and doc.owner_id == users[0].id
    )
    db.add(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content="content",
            char_start=0,
            char_end=7,
            embedding=[1.0] + [0.0] * 767,
        )
    )
    db.commit()
    doc_id = doc.id
    assert signed_in.delete(f"/api/documents/{doc_id}").status_code == 204
    db.expire_all()
    assert db.get(Document, doc_id) is None
    assert db.scalar(select(DocumentChunk)) is None


def test_upload_size_and_signature(signed_in, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_BYTES", 1024)
    assert (
        signed_in.post(
            "/api/documents/upload", files={"file": ("large.txt", b"x" * 1025, "text/plain")}
        ).status_code
        == 413
    )
    assert (
        signed_in.post(
            "/api/documents/upload", files={"file": ("fake.pdf", b"not a PDF", "application/pdf")}
        ).status_code
        == 422
    )


def test_request_body_limit(signed_in):
    response = signed_in.post(
        "/api/chat/", content=b"x" * 65537, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_input_validation(signed_in):
    conv = signed_in.post("/api/chat/", json={}).json()["id"]
    for payload in (
        {"content": "", "query_mode": "qa"},
        {"query_mode": "agent"},
        {"query_mode": "summary"},
        {"content": "x" * 4001},
    ):
        response = signed_in.post(
            f"/api/chat/{conv}/message", json={**payload, "request_id": str(uuid.uuid4())}
        )
        assert response.status_code == 422
    assert signed_in.get("/api/chat/not-a-uuid/history").status_code == 422


def test_rate_limit_is_shared_between_sessions(db):
    from fastapi import HTTPException

    from app.db.database import SessionLocal

    enforce_limit(db, "test-limit", 1)
    with SessionLocal() as other, pytest.raises(HTTPException) as error:
        enforce_limit(other, "test-limit", 1)
    assert error.value.status_code == 429


def test_failed_login_is_generic(client, users):
    for email in (users[0].email, "missing@example.com"):
        response = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password."


def test_readiness_requires_worker(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    from app.worker import heartbeat

    heartbeat("test-worker")
    assert client.get("/ready").status_code == 200
