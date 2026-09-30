from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limit import enforce_limit
from app.core.security import (
    COOKIE_NAME,
    DUMMY_HASH,
    new_session,
    password_hasher,
    require_user,
    token_hash,
    verify_password,
)
from app.db.database import get_db
from app.db.models import AuthSession, User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class Login(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    enforce_limit(db, f"login-ip:{ip}", settings.LOGIN_REQUESTS_PER_MINUTE)
    enforce_limit(db, f"login-account:{email}", settings.LOGIN_REQUESTS_PER_MINUTE)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, "Invalid email or password.")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(body.password)
    old = request.cookies.get(COOKIE_NAME)
    if old:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(old)))
    token, session = new_session(db, user)
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.SESSION_HOURS * 3600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/api",
    )
    return {"email": user.email, "csrf_token": session.csrf_token}


@router.get("/me")
def me(request: Request, user: User = Depends(require_user)):
    return {"email": user.email, "csrf_token": request.state.auth_session.csrf_token}


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/api", secure=settings.COOKIE_SECURE, httponly=True, samesite="strict"
    )
