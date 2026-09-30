from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is required. See .env.example.")
db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
options = {"pool_pre_ping": True}
if db_url.startswith("sqlite"):
    if settings.ENVIRONMENT != "test":
        raise ValueError("SQLite is supported only for isolated tests")
    options["connect_args"] = {"check_same_thread": False}
else:
    options.update(
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=15000"},
    )
engine = create_engine(db_url, **options)
if db_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
