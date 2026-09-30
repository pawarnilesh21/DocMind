import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Conversation, Document, Message
from app.services import llm_service, retrieval_service
from app.services.qa_pipeline import run_qa
from app.worker import claim_job


@pytest.mark.integration
def test_two_workers_claim_distinct_jobs(db, users):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency test")
    for index in range(2):
        db.add(
            Document(
                owner_id=users[0].id,
                filename=f"job{index}.txt",
                file_type="txt",
                file_size=5,
                source_bytes=b"hello",
                status="queued",
            )
        )
    db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda _: claim_job(), range(2)))
    assert len({job[0] for job in jobs}) == 2
    assert claim_job() is None


@pytest.mark.integration
def test_concurrent_chat_is_rejected_without_duplicate_messages(db, users, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency test")
    conv = Conversation(owner_id=users[0].id, title="test")
    db.add(conv)
    db.commit()
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(retrieval_service, "retrieve", Mock(return_value=[]))

    def answer(*args):
        entered.set()
        assert release.wait(5)
        return {"answer": "No context", "sources_used": [], "token_usage": {}, "grounding": "abstained"}

    monkeypatch.setattr(llm_service, "generate_answer", answer)

    def first():
        with SessionLocal() as session:
            return run_qa(session, "question", conv.id, owner_id=users[0].id, request_id=uuid.uuid4())

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert entered.wait(5)
            with SessionLocal() as session, pytest.raises(HTTPException) as error:
                run_qa(session, "overlap", conv.id, owner_id=users[0].id, request_id=uuid.uuid4())
            assert error.value.status_code == 409
        finally:
            release.set()
        future.result(timeout=5)
    assert len(db.scalars(select(Message)).all()) == 2


def test_source_deleted_during_answer_is_not_saved(db, users, monkeypatch):
    doc = Document(owner_id=users[0].id, filename="file.txt", file_type="txt", file_size=5, status="ready")
    conv = Conversation(owner_id=users[0].id, title="test")
    db.add_all([doc, conv])
    db.commit()
    doc_id = doc.id
    monkeypatch.setattr(retrieval_service, "retrieve", Mock(return_value=[]))

    def answer(*args):
        with SessionLocal() as other:
            other.delete(other.get(Document, doc_id))
            other.commit()
        return {
            "answer": "Deleted content",
            "sources_used": [
                {"document_id": str(doc_id), "filename": "file.txt", "chunk_index": 0, "page_number": None}
            ],
            "token_usage": {},
            "grounding": "verified",
        }

    monkeypatch.setattr(llm_service, "generate_answer", answer)
    with pytest.raises(HTTPException) as error:
        run_qa(db, "question", conv.id, owner_id=users[0].id, request_id=uuid.uuid4())
    assert error.value.status_code == 409
    assert db.scalar(select(Message)) is None
    db.refresh(conv)
    assert conv.busy_token is None
