"""Vectors live with their source chunks in PostgreSQL, in the same transaction."""

from sqlalchemy import select

from app.config import settings
from app.db.models import Document, DocumentChunk


def query_similar(db, query_embedding, *, owner_id, n_results=8, document_ids=None):
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == owner_id,
            Document.status == "ready",
            DocumentChunk.embedding_model == settings.EMBEDDING_MODEL,
            DocumentChunk.embedding.is_not(None),
        )
    )
    if document_ids:
        statement = statement.where(Document.id.in_(document_ids))
    return db.execute(statement.order_by(distance).limit(n_results)).all()
