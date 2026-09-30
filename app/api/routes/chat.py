from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limit import enforce_limit
from app.core.security import require_user
from app.db.database import get_db
from app.db.models import Conversation, Message, User
from app.schemas.chat import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from app.services.qa_pipeline import owned_conversation, run_qa

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/", response_model=ConversationResponse, status_code=201)
def create_conversation(
    body: ConversationCreate, db: Session = Depends(get_db), user: User = Depends(require_user)
):
    enforce_limit(db, f"new-chat:{user.id}", 20)
    conv = Conversation(owner_id=user.id, title=body.title)
    db.add(conv)
    db.commit()
    return conv


@router.post("/{conversation_id}/message", response_model=MessageResponse)
def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    owned_conversation(db, conversation_id, user.id)
    enforce_limit(db, f"chat:{user.id}", settings.CHAT_REQUESTS_PER_MINUTE)
    enforce_limit(db, f"chat-day:{user.id}", settings.CHAT_REQUESTS_PER_DAY, 86400)
    return run_qa(
        db,
        body.content,
        conversation_id,
        owner_id=user.id,
        request_id=body.request_id,
        document_ids=body.document_ids,
        query_mode=body.query_mode,
    )


@router.get("/{conversation_id}/history", response_model=ConversationDetailResponse)
def history(
    conversation_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    conv = owned_conversation(db, conversation_id, user.id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .offset(offset)
        .limit(limit + 1)
    ).all()
    return {
        **ConversationResponse.model_validate(conv).model_dump(),
        "messages": messages[:limit][::-1],
        "has_more": len(messages) > limit,
    }


@router.get("/", response_model=list[ConversationResponse])
def conversations(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return db.scalars(
        select(Conversation)
        .where(Conversation.owner_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_user)
):
    db.delete(owned_conversation(db, conversation_id, user.id))
    db.commit()
