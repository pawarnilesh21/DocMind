from datetime import timedelta
from unittest.mock import Mock

from sqlalchemy import select

from app.config import settings
from app.db.models import Document, DocumentChunk, utcnow
from app.services import ingestion_pipeline
from app.worker import claim_job, fail_job


def queued_document(db, owner):
    doc = Document(
        owner_id=owner.id,
        filename="test.txt",
        file_type="txt",
        file_size=18,
        source_bytes=b"some test document",
        status="queued",
    )
    db.add(doc)
    db.commit()
    return doc


def test_job_claim_and_atomic_index(db, users, monkeypatch):
    doc = queued_document(db, users[0])
    monkeypatch.setattr(
        ingestion_pipeline, "generate_embeddings", lambda texts: [[1.0] + [0.0] * 767 for _ in texts]
    )
    job = claim_job()
    assert job[0] == doc.id
    assert claim_job() is None
    ingestion_pipeline.ingest_document(*job)
    db.expire_all()
    assert db.get(Document, doc.id).status == "ready"
    chunks = db.scalars(select(DocumentChunk)).all()
    assert len(chunks) == 1
    assert len(chunks[0].embedding) == 768


def test_delete_during_embedding_cannot_resurrect_document(db, users, monkeypatch):
    doc = queued_document(db, users[0])
    job = claim_job()

    def delete_and_embed(texts):
        from app.db.database import SessionLocal

        with SessionLocal() as session:
            session.delete(session.get(Document, doc.id))
            session.commit()
        return [[1.0] + [0.0] * 767 for _ in texts]

    monkeypatch.setattr(ingestion_pipeline, "generate_embeddings", delete_and_embed)
    ingestion_pipeline.ingest_document(*job)
    db.expire_all()
    assert db.get(Document, job[0]) is None
    assert db.scalar(select(DocumentChunk)) is None


def test_provider_failure_leaves_no_partial_chunks(db, users, monkeypatch):
    import pytest

    doc = queued_document(db, users[0])
    job = claim_job()
    monkeypatch.setattr(
        ingestion_pipeline, "generate_embeddings", Mock(side_effect=RuntimeError("provider down"))
    )
    with pytest.raises(RuntimeError):
        ingestion_pipeline.ingest_document(*job)
    fail_job(*job)
    db.expire_all()
    assert db.get(Document, doc.id).status == "queued"
    assert db.scalar(select(DocumentChunk)) is None


def test_expired_lease_reclaimed_and_stale_job_ignored(db, users, monkeypatch):
    doc = queued_document(db, users[0])
    stale = claim_job()
    db.refresh(doc)
    doc.lease_until = utcnow() - timedelta(seconds=1)
    db.commit()
    fresh = claim_job()
    assert fresh[1] != stale[1]
    model = Mock()
    monkeypatch.setattr(ingestion_pipeline, "generate_embeddings", model)
    ingestion_pipeline.ingest_document(*stale)
    model.assert_not_called()


def test_exhausted_job_becomes_failed(db, users):
    doc = queued_document(db, users[0])
    claim_job()
    db.refresh(doc)
    doc.attempts = settings.JOB_MAX_ATTEMPTS
    doc.lease_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert claim_job() is None
    db.refresh(doc)
    assert doc.status == "failed"
