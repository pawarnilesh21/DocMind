from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    file_type: str
    file_size: int
    total_chunks: int
    status: str
    uploaded_at: datetime
    metadata_: dict | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    has_more: bool = False


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    page_number: int | None
    char_start: int
    char_end: int
