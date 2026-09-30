from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db.models import Document
from app.services import embedding_service, vector_store


def validate_documents(db, owner_id, document_ids):
    if not document_ids:
        return
    ids = set(document_ids)
    docs = db.scalars(select(Document).where(Document.id.in_(ids), Document.owner_id == owner_id)).all()
    if len(docs) != len(ids):
        raise HTTPException(404, "Document not found.")
    if any(doc.status != "ready" for doc in docs):
        raise HTTPException(409, "Wait until all selected documents finish processing.")


def retrieve(db, query, *, owner_id, top_k=8, document_ids=None):
    validate_documents(db, owner_id, document_ids)
    ready = select(Document.id).where(Document.owner_id == owner_id, Document.status == "ready")
    if document_ids:
        ready = ready.where(Document.id.in_(document_ids))
    if db.scalar(ready.limit(1)) is None:
        return []
    db.commit()  # Never hold a transaction while waiting for a provider.
    embedding = embedding_service.generate_embeddings([query], query=True)[0]
    matches = vector_store.query_similar(
        db, embedding, owner_id=owner_id, n_results=top_k, document_ids=document_ids
    )
    chunks = []
    for chunk, filename, distance in matches:
        score = 1 - float(distance)
        if score >= settings.SIMILARITY_THRESHOLD:
            chunks.append(
                {
                    "content": chunk.content,
                    "score": score,
                    "document_id": str(chunk.document_id),
                    "filename": filename,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                }
            )
    return chunks
