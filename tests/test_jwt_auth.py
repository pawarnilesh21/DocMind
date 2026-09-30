import time

import jwt
import pytest
from sqlalchemy import delete, select

from app.config import Settings, settings
from app.core.security import token_hash
from app.db.models import AuthSession


def claims_for(token):
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


def test_login_issues_signed_jwt(signed_in, users, db):
    token = signed_in.cookies.get("docmind_session")
    claims = claims_for(token)
    assert claims["sub"] == str(users[0].id)
    assert claims["jti"]
    assert claims["exp"] > claims["iat"]
    assert db.get(AuthSession, token_hash(token)) is not None
    assert signed_in.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "kind",
    ["expired", "future", "issuer", "audience", "missing", "signature", "algorithm", "subject", "legacy"],
)
def test_invalid_jwt_rejected_even_with_database_record(signed_in, db, users, kind):
    old = signed_in.cookies.get("docmind_session")
    claims = claims_for(old)
    key = settings.JWT_SECRET_KEY.get_secret_value()
    algorithm = "HS256"
    if kind == "expired":
        claims["exp"] = int(time.time()) - 60
    elif kind == "future":
        claims["nbf"] = int(time.time()) + 600
    elif kind == "issuer":
        claims["iss"] = "other-app"
    elif kind == "audience":
        claims["aud"] = "other-client"
    elif kind == "missing":
        del claims["exp"]
    elif kind == "signature":
        key = "wrong-signing-key-" * 4
    elif kind == "algorithm":
        algorithm = "HS384"
    elif kind == "subject":
        claims["sub"] = str(users[1].id)
    token = jwt.encode(claims, key, algorithm=algorithm) if kind != "legacy" else "old-opaque-token"
    session = db.get(AuthSession, token_hash(old))
    session.token_hash = token_hash(token)
    db.commit()
    signed_in.cookies.clear()
    signed_in.cookies.set("docmind_session", token, path="/api")
    assert signed_in.get("/api/auth/me").status_code == 401


def test_logout_revokes_copied_jwt(signed_in):
    token = signed_in.cookies.get("docmind_session")
    assert signed_in.post("/api/auth/logout").status_code == 204
    signed_in.cookies.set("docmind_session", token, path="/api")
    assert signed_in.get("/api/auth/me").status_code == 401


def test_database_revocation_invalidates_valid_jwt(signed_in, db):
    db.execute(delete(AuthSession))
    db.commit()
    assert signed_in.get("/api/auth/me").status_code == 401


def test_disabled_account_rejects_valid_jwt(signed_in, users, db):
    users[0].active = False
    db.commit()
    assert signed_in.get("/api/auth/me").status_code == 401


def test_relogin_revokes_previous_jwt(signed_in, users, db):
    old = signed_in.cookies.get("docmind_session")
    response = signed_in.post(
        "/api/auth/login", json={"email": users[0].email, "password": "long-test-password"}
    )
    assert response.status_code == 200
    assert signed_in.cookies.get("docmind_session") != old
    assert len(db.scalars(select(AuthSession)).all()) == 1
    signed_in.cookies.clear()
    signed_in.cookies.set("docmind_session", old, path="/api")
    assert signed_in.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("key", ["", "short", "replace_with_a_random_secret_of_at_least_32_bytes"])
def test_missing_or_placeholder_signing_key_rejected(key):
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, JWT_SECRET_KEY=key)
