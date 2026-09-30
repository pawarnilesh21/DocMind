import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import deferred, relationship

from app.db.database import Base


def utcnow():
    # Existing schema stores UTC without timezone; retain compatibility.
    return datetime.now(UTC).replace(tzinfo=None)


json_type = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key = Column(String(64), primary_key=True)
    count = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id = Column(String(64), primary_key=True)
    seen_at = Column(DateTime, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Only quarantined legacy records may have no owner.
    owner_id = Column(Uuid, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    total_chunks = Column(Integer, default=0)
    status = Column(String, default="queued", index=True)
    uploaded_at = Column(DateTime, default=utcnow)
    metadata_ = Column("metadata", json_type, default=dict)
    source_bytes = deferred(Column(LargeBinary, nullable=True))
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(Uuid, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    next_attempt_at = Column(DateTime, nullable=False, default=utcnow)
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    embedding = deferred(Column(Vector(768), nullable=True))
    embedding_model = Column(String, nullable=True)
    document = relationship("Document", back_populates="chunks")
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    busy_token = Column(Uuid, nullable=True)
    busy_until = Column(DateTime, nullable=True)
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id = Column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(json_type, default=list)
    query_mode = Column(String, nullable=False, default="qa")
    created_at = Column(DateTime, default=utcnow)
    metadata_ = Column("metadata", json_type, default=dict)
    request_id = Column(Uuid, nullable=True)
    conversation = relationship("Conversation", back_populates="messages")
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        UniqueConstraint("conversation_id", "request_id", "role", name="uq_message_request_role"),
    )
