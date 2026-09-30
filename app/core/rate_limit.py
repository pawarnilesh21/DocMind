import hashlib
import time
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import RateLimit


def enforce_limit(db, identity: str, limit: int, seconds: int = 60):
    window = int(time.time()) // seconds
    key = hashlib.sha256(f"{identity}:{window}".encode()).hexdigest()
    expires = datetime.fromtimestamp((window + 1) * seconds, UTC).replace(tzinfo=None)
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    stmt = insert(RateLimit).values(key=key, count=1, expires_at=expires)
    stmt = stmt.on_conflict_do_update(
        index_elements=[RateLimit.key], set_={"count": RateLimit.count + 1}
    ).returning(RateLimit.count)
    count = db.execute(stmt).scalar_one()
    db.commit()
    if count > limit:
        raise HTTPException(
            429,
            "Request limit reached. Please try again later.",
            headers={"Retry-After": str(max(1, (window + 1) * seconds - int(time.time())))},
        )
