import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import AuthSession, User, utcnow

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
COOKIE_NAME = "docmind_session"


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(password, hashed):
    try:
        return password_hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def new_session(db, user):
    now = datetime.now(UTC)
    expires = now + timedelta(hours=settings.SESSION_HOURS)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "jti": secrets.token_urlsafe(32),
            "iat": now,
            "nbf": now,
            "exp": expires,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )
    session = AuthSession(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_hex(32),
        expires_at=expires.replace(tzinfo=None),
    )
    db.add(session)
    return token, session


def require_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["sub", "jti", "iat", "nbf", "exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Please sign in.") from None
    session = db.get(AuthSession, token_hash(token)) if token else None
    if not session or session.expires_at <= utcnow() or claims["sub"] != str(session.user_id):
        raise HTTPException(401, "Please sign in.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Please sign in.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "Session verification failed. Refresh and try again.")
    request.state.auth_session = session
    return user
