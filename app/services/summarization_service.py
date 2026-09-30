from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import DocumentChunk
from app.services.document_service import get_document_by_id
from app.services.llm_service import generate_answer

# Bound provider cost and context use. Never silently summarize only part of a document.
MAX_SUMMARY_CHARS = 36_000


def summarize_document(db, document_id, owner_id):
    doc = get_document_by_id(db, document_id, owner_id)
    if doc.status != "ready":
        raise HTTPException(409, "Wait until the document is ready.")
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    if sum(len(c.content) for c in chunks) > MAX_SUMMARY_CHARS:
        raise HTTPException(
            422,
            "This document exceeds the summary limit. Use targeted questions or upload a shorter document.",
        )
    context = [
        {
            "content": c.content,
            "document_id": str(doc.id),
            "filename": doc.filename,
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
        }
        for c in chunks
    ]
    db.commit()
    return generate_answer("Summarize this document's main facts and qualifications.", context, summary=True)
