# Schemas for retrieval operations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    content: str
    score: float
    document_id: str
    chunk_index: int
    page_number: int | None = None
    filename: str


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 5
    document_ids: list[str] | None = None


class RetrievalResponse(BaseModel):
    chunks: list[RetrievedChunk]
    query: str
