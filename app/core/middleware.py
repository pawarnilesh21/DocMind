import asyncio
import json
import logging
import time
import uuid

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.core.rate_limit import enforce_limit
from app.core.security import require_user
from app.db.database import SessionLocal

log = logging.getLogger("docmind.http")


def authorize_upload(scope):
    with SessionLocal() as db:
        user = require_user(Request(scope), db)
        enforce_limit(db, f"upload:{user.id}", settings.UPLOAD_REQUESTS_PER_HOUR, 3600)


class RequestControls:
    """Bound request bytes before multipart/JSON parsing, check origins, and log no payloads."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        headers = Headers(scope=scope)
        started = time.monotonic()
        status = 500

        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                ]
            await send(message)

        try:
            if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                origin = headers.get("origin")
                if (origin and origin not in settings.ALLOWED_ORIGINS) or headers.get(
                    "x-requested-with"
                ) != "DocMind":
                    return await JSONResponse({"detail": "Request origin rejected."}, 403)(
                        scope, receive, tracked_send
                    )
                if scope["path"] == "/api/documents/upload":
                    try:
                        await run_in_threadpool(authorize_upload, scope)
                    except HTTPException as exc:
                        return await JSONResponse(
                            {"detail": exc.detail}, exc.status_code, headers=exc.headers
                        )(scope, receive, tracked_send)
                limit = (
                    settings.MAX_FILE_BYTES + 1024 * 1024
                    if scope["path"] == "/api/documents/upload"
                    else 64 * 1024
                )
                size_header = headers.get("content-length")
                if size_header:
                    try:
                        oversized = int(size_header) > limit or int(size_header) < 0
                    except ValueError:
                        oversized = True
                    if oversized:
                        return await JSONResponse({"detail": "Request is too large."}, 413)(
                            scope, receive, tracked_send
                        )
                body = bytearray()
                deadline = time.monotonic() + 30
                while True:
                    try:
                        message = await asyncio.wait_for(
                            receive(), timeout=max(0.01, deadline - time.monotonic())
                        )
                    except TimeoutError:
                        return await JSONResponse({"detail": "Request upload timed out."}, 408)(
                            scope, receive, tracked_send
                        )
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > limit:
                        return await JSONResponse({"detail": "Request is too large."}, 413)(
                            scope, receive, tracked_send
                        )
                    if not message.get("more_body", False):
                        break
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                await self.app(scope, replay, tracked_send)
            else:
                await self.app(scope, receive, tracked_send)
        finally:
            # Paths contain IDs, so log route templates only.
            route = getattr(scope.get("route"), "path", "unmatched")
            log.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": route,
                        "status": status,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            )
