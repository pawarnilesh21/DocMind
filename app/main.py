import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import auth, chat, documents
from app.config import settings
from app.core.middleware import RequestControls
from app.db.database import SessionLocal, engine
from app.db.models import WorkerHeartbeat, utcnow
from app.services.provider import ProviderError

log = logging.getLogger("docmind")


@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("application_started version=%s environment=%s", settings.APP_VERSION, settings.ENVIRONMENT)
    yield
    engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)
app.add_middleware(RequestControls)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Requested-With"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)


@app.exception_handler(ProviderError)
async def provider_failure(request: Request, exc: ProviderError):
    log.warning("provider_failure request_id=%s", getattr(request.state, "request_id", "unknown"))
    return JSONResponse(
        {"detail": "The AI service is unavailable. Please retry shortly."}, 503, headers={"Retry-After": "10"}
    )


@app.exception_handler(SQLAlchemyError)
async def database_failure(request: Request, exc: SQLAlchemyError):
    log.error(
        "database_failure request_id=%s error_type=%s",
        getattr(request.state, "request_id", "unknown"),
        type(exc).__name__,
    )
    return JSONResponse({"detail": "The data service is unavailable. Please retry shortly."}, 503)


@app.exception_handler(Exception)
async def unexpected_failure(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    log.error("unhandled_failure request_id=%s error_type=%s", request_id, type(exc).__name__)
    return JSONResponse({"detail": "An unexpected error occurred.", "request_id": request_id}, 500)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/ready")
def ready():
    try:
        with SessionLocal() as db:
            if db.bind.dialect.name == "postgresql":
                revision = db.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != "20260914_production":
                    return JSONResponse({"status": "not_ready"}, 503)
                db.execute(text("SELECT '[1,0]'::vector <=> '[1,0]'::vector"))
            worker = db.scalar(
                select(WorkerHeartbeat.id)
                .where(WorkerHeartbeat.seen_at > utcnow() - timedelta(seconds=60))
                .limit(1)
            )
            if not worker:
                return JSONResponse({"status": "not_ready"}, 503)
        return {"status": "ready"}
    except SQLAlchemyError:
        return JSONResponse({"status": "not_ready"}, 503)


app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
