from sqlalchemy import delete, select

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Document, DocumentChunk
from app.services.chunker import split_pages
from app.services.embedding_service import generate_embeddings
from app.services.parser import InvalidDocument, parse_pages


def ingest_document(document_id, lease_token):
    # Copy bounded inputs and close the read transaction before any provider request.
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if not doc or doc.lease_token != lease_token or doc.status != "processing":
            return
        if doc.source_bytes is not None:
            data, file_type = doc.source_bytes, doc.file_type
            legacy_chunks = None
        else:
            data, file_type = None, None
            legacy_chunks = [
                {
                    k: getattr(c, k)
                    for k in ("chunk_index", "content", "page_number", "char_start", "char_end")
                }
                for c in db.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == document_id)
                    .order_by(DocumentChunk.chunk_index)
                )
            ]
    chunks = split_pages(parse_pages(data, file_type)) if data is not None else legacy_chunks
    if (
        not chunks
        or len(chunks) > settings.MAX_CHUNKS
        or sum(len(c["content"]) for c in chunks) > settings.MAX_EXTRACTED_CHARS * 2
    ):
        raise InvalidDocument("No usable text or document exceeds indexing limits.")
    vectors = generate_embeddings([c["content"] for c in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding count mismatch")
    with SessionLocal() as db:
        doc = db.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.lease_token == lease_token,
                Document.status == "processing",
            )
            .with_for_update()
        )
        if not doc:
            return  # Deleted or reclaimed while this job ran.
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        for chunk, vector in zip(chunks, vectors, strict=True):
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    **chunk,
                    embedding=vector,
                    embedding_model=settings.EMBEDDING_MODEL,
                )
            )
        doc.status, doc.total_chunks = "ready", len(chunks)
        doc.lease_token, doc.lease_until = None, None
        doc.metadata_ = {
            "embedding_model": settings.EMBEDDING_MODEL,
            "page_citations_available": any(c["page_number"] for c in chunks),
        }
        db.commit()  # Text, embeddings, and ready status become visible together.
