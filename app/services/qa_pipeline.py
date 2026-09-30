import hashlib
import json
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from app.config import settings
from app.db.models import Conversation, Document, Message, utcnow
from app.services import llm_service, retrieval_service, summarization_service
from app.services.provider import budget


def owned_conversation(db, conversation_id, owner_id):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    return conv


def run_qa(db, query, conversation_id, *, owner_id, request_id, document_ids=None, query_mode="qa"):
    owned_conversation(db, conversation_id, owner_id)
    fingerprint = hashlib.sha256(
        json.dumps([query, query_mode, sorted(str(d) for d in (document_ids or []))]).encode()
    ).hexdigest()
    previous = db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.request_id == request_id,
            Message.role == "assistant",
        )
    )
    if previous:
        if (previous.metadata_ or {}).get("request_fingerprint") != fingerprint:
            raise HTTPException(409, "This request ID was already used for another message.")
        return previous
    token = uuid.uuid4()
    now = utcnow()
    # The lease makes overlapping requests explicit, without a database lock across network calls.
    acquired = db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.owner_id == owner_id,
            (Conversation.busy_until.is_(None)) | (Conversation.busy_until < now),
        )
        .values(busy_token=token, busy_until=now + timedelta(seconds=300))
    ).rowcount
    db.commit()
    if not acquired:
        raise HTTPException(409, "This conversation is generating an answer. Try again shortly.")
    try:
        history = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id)
            .limit(6)
        ).all()[::-1]
        with budget(120):
            if query_mode == "summary":
                result = summarization_service.summarize_document(db, document_ids[0], owner_id)
            else:
                chunks = retrieval_service.retrieve(db, query, owner_id=owner_id, document_ids=document_ids)
                db.commit()
                result = llm_service.generate_answer(query, chunks, history)
        # Recheck sources and ownership under shared locks, so concurrent deletion cannot
        # commit between validation and saving an answer.
        used_ids = {uuid.UUID(s["document_id"]) for s in result["sources_used"]}
        if used_ids:
            still_ready = db.scalars(
                select(Document.id)
                .where(Document.id.in_(used_ids), Document.owner_id == owner_id, Document.status == "ready")
                .with_for_update(read=True)
            ).all()
            if set(still_ready) != used_ids:
                raise HTTPException(
                    409, "A source document changed while generating the answer. Please retry."
                )
        conv = db.scalar(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.owner_id == owner_id,
                Conversation.busy_token == token,
            )
            .with_for_update()
        )
        if not conv:
            raise HTTPException(409, "The conversation changed. Please retry.")
        if not conv.title or conv.title == "New Conversation":
            conv.title = (query or "Document summary")[:80]
        conv.updated_at = utcnow()
        user_message = Message(
            conversation_id=conversation_id,
            role="user",
            content=query or "Summarize this document.",
            query_mode=query_mode,
            request_id=request_id,
            sources=[],
            metadata_={},
        )
        assistant = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=result["answer"],
            sources=result["sources_used"],
            query_mode=query_mode,
            request_id=request_id,
            metadata_={
                "token_usage": result["token_usage"],
                "grounding": result["grounding"],
                "request_fingerprint": fingerprint,
                "model": settings.LLM_MODEL,
            },
        )
        db.add_all([user_message, assistant])
        conv.busy_token, conv.busy_until = None, None
        db.commit()
        return assistant
    except Exception:
        db.rollback()
        db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.busy_token == token)
            .values(busy_token=None, busy_until=None)
        )
        db.commit()
        raise
