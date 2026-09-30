"""Operator-only account provisioning and explicit legacy data adoption."""

import argparse
import getpass

from sqlalchemy import delete, select, update

from app.core.security import password_hasher
from app.db.database import SessionLocal
from app.db.models import AuthSession, Conversation, Document, User, utcnow


def password():
    value = getpass.getpass("Password (12-128 characters): ")
    if not 12 <= len(value) <= 128:
        raise SystemExit("Password must contain 12-128 characters.")
    if value != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")
    return password_hasher.hash(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["create-user", "reset-password", "disable-user", "claim-legacy", "reindex"]
    )
    parser.add_argument("email")
    parser.add_argument(
        "--confirm", action="store_true", help="Required when assigning legacy data or reindexing."
    )
    args = parser.parse_args()
    email = args.email.strip().lower()
    if len(email) > 254 or "@" not in email or any(c.isspace() for c in email):
        raise SystemExit("Provide a valid email address.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.command == "create-user":
            if user:
                raise SystemExit("An account with this email already exists.")
            db.add(User(email=email, password_hash=password()))
        else:
            if not user:
                raise SystemExit("Account not found.")
            if args.command == "reset-password":
                user.password_hash = password()
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
            elif args.command == "disable-user":
                user.active = False
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
            elif args.command == "claim-legacy":
                if not args.confirm:
                    raise SystemExit(
                        "This assigns ALL unowned documents and chats to this account. Re-run with --confirm after review."
                    )
                db.execute(
                    update(Document)
                    .where(Document.owner_id.is_(None))
                    .values(
                        owner_id=user.id,
                        status="queued",
                        attempts=0,
                        next_attempt_at=utcnow(),
                        lease_token=None,
                        lease_until=None,
                    )
                )
                db.execute(
                    update(Conversation).where(Conversation.owner_id.is_(None)).values(owner_id=user.id)
                )
            elif args.command == "reindex":
                if not args.confirm:
                    raise SystemExit(
                        "Reindexing temporarily hides this account's documents and incurs embedding costs. Re-run with --confirm."
                    )
                db.execute(
                    update(Document)
                    .where(Document.owner_id == user.id)
                    .values(
                        status="queued",
                        attempts=0,
                        next_attempt_at=utcnow(),
                        lease_token=None,
                        lease_until=None,
                    )
                )
        db.commit()
    print("Operation completed.")


if __name__ == "__main__":
    main()
