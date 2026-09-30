from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limit import enforce_limit
from app.core.security import require_user
from app.db.database import get_db
from app.db.models import Document, DocumentChunk, User
from app.schemas.document import DocumentChunkResponse, DocumentListResponse, DocumentResponse
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=202)
def upload_document(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_user)
):
    return document_service.process_and_store_document(file, db, user.id)


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    docs = db.scalars(
        select(Document)
        .where(Document.owner_id == user.id)
        .order_by(Document.uploaded_at.desc(), Document.id)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    return {"documents": docs[:limit], "has_more": len(docs) > limit}


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return document_service.get_document_by_id(db, document_id, user.id)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def get_chunks(
    document_id: UUID,
    chunk_index: int | None = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    document_service.get_document_by_id(db, document_id, user.id)
    stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    if chunk_index is not None:
        stmt = stmt.where(DocumentChunk.chunk_index == chunk_index)
    return db.scalars(stmt.order_by(DocumentChunk.chunk_index).offset(offset).limit(limit)).all()


@router.post("/{document_id}/retry", response_model=DocumentResponse, status_code=202)
def retry(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_user)):
    enforce_limit(db, f"upload:{user.id}", settings.UPLOAD_REQUESTS_PER_HOUR, 3600)
    return document_service.retry_document(db, document_id, user.id)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_user)):
    document_service.delete_document(db, document_id, user.id)
