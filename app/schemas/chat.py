from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceCitation(BaseModel):
    document_id: str
    chunk_index: int
    page_number: int | None = None
    filename: str


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=4000)
    query_mode: Literal["qa", "summary"] = "qa"
    document_ids: list[UUID] | None = Field(default=None, max_length=20)
    request_id: UUID

    @model_validator(mode="after")
    def validate_mode(self):
        self.content = self.content.strip()
        if self.query_mode == "qa" and not self.content:
            raise ValueError("A question is required")
        if self.query_mode == "summary" and (not self.document_ids or len(set(self.document_ids)) != 1):
            raise ValueError("Select exactly one document for a summary")
        return self


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    query_mode: str
    created_at: datetime
    metadata_: dict | None = None


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", min_length=1, max_length=120)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]
    has_more: bool = False
