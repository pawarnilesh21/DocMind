from pathlib import PurePath

from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import settings
from app.db.models import Document, User, utcnow
from app.services.parser import InvalidDocument, validate_file

MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


def get_document_by_id(db, document_id, owner_id):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner_id))
    if not doc:
        raise HTTPException(404, "Document not found.")
    return doc


def process_and_store_document(file, db, owner_id):
    file_type = MIME_TYPES.get(file.content_type)
    if not file_type:
        raise HTTPException(415, "Supported formats are PDF, DOCX, and UTF-8 TXT.")
    data = bytearray()
    while block := file.file.read(64 * 1024):
        data.extend(block)
        if len(data) > settings.MAX_FILE_BYTES:
            raise HTTPException(413, "The file exceeds the upload limit.")
    try:
        validate_file(bytes(data), file_type)
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc)) from None
    # Serialize quota checks for a user, including concurrent uploads.
    db.scalar(select(User).where(User.id == owner_id).with_for_update())
    count = db.scalar(select(func.count()).select_from(Document).where(Document.owner_id == owner_id))
    if count >= settings.MAX_DOCUMENTS_PER_USER:
        raise HTTPException(409, "Document quota reached. Delete a document before uploading another.")
    filename = PurePath((file.filename or "document").replace("\\", "/")).name
    filename = "".join(c for c in filename if c.isprintable())[:200] or "document"
    document = Document(
        owner_id=owner_id,
        filename=filename,
        file_type=file_type,
        file_size=len(data),
        source_bytes=bytes(data),
        status="queued",
        total_chunks=0,
        metadata_={},
    )
    db.add(document)
    db.commit()
    return document


def delete_document(db, document_id, owner_id):
    document = get_document_by_id(db, document_id, owner_id)
    # The database FK deletes text and vectors atomically; a running job cannot recreate it.
    db.delete(document)
    db.commit()


def retry_document(db, document_id, owner_id):
    doc = db.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == owner_id).with_for_update()
    )
    if not doc:
        raise HTTPException(404, "Document not found.")
    if doc.status != "failed":
        raise HTTPException(409, "Only failed documents can be retried.")
    doc.status, doc.attempts, doc.next_attempt_at = "queued", 0, utcnow()
    doc.metadata_ = {}
    db.commit()
    return doc
