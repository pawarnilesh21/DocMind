"""Durable PostgreSQL jobs, process isolation, hard deadlines, leases, and retry recovery."""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import AuthSession, Document, RateLimit, WorkerHeartbeat, utcnow

log = logging.getLogger("docmind.worker")
stopping = False


def claim_job():
    now = utcnow()
    with SessionLocal() as db:
        db.execute(
            update(Document)
            .where(
                Document.status == "processing",
                Document.lease_until < now,
                Document.attempts >= settings.JOB_MAX_ATTEMPTS,
            )
            .values(
                status="failed",
                lease_token=None,
                lease_until=None,
                metadata_={"error": "Processing stopped repeatedly. Retry the document."},
            )
        )
        doc = db.scalar(
            select(Document)
            .where(
                Document.owner_id.is_not(None),
                Document.attempts < settings.JOB_MAX_ATTEMPTS,
                or_(
                    (Document.status == "queued") & (Document.next_attempt_at <= now),
                    (Document.status == "processing") & (Document.lease_until < now),
                ),
            )
            .order_by(Document.next_attempt_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not doc:
            db.commit()
            return None
        token = uuid.uuid4()
        doc.status, doc.lease_token = "processing", token
        doc.lease_until = now + timedelta(seconds=settings.JOB_TIMEOUT_SECONDS + 30)
        doc.attempts += 1
        db.commit()
        return doc.id, token


def fail_job(doc_id, token, *, permanent=False, message="Processing failed. It will retry automatically."):
    with SessionLocal() as db:
        doc = db.scalar(
            select(Document).where(Document.id == doc_id, Document.lease_token == token).with_for_update()
        )
        if not doc:
            return
        failed = permanent or doc.attempts >= settings.JOB_MAX_ATTEMPTS
        doc.status = "failed" if failed else "queued"
        doc.next_attempt_at = utcnow() + timedelta(seconds=min(60, 5 * 2**doc.attempts))
        doc.lease_token, doc.lease_until = None, None
        doc.metadata_ = {
            "error": message
            if not failed or permanent
            else "Processing failed after retries. Please retry later."
        }
        db.commit()


def heartbeat(worker_id):
    with SessionLocal() as db:
        db.merge(WorkerHeartbeat(id=worker_id, seen_at=utcnow()))
        db.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.seen_at < utcnow() - timedelta(days=1)))
        db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
        db.execute(delete(RateLimit).where(RateLimit.expires_at < utcnow()))
        db.commit()


def run_child(doc_id, token):
    # POSIX deployments also impose process memory and CPU limits on untrusted parsers.
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (settings.JOB_TIMEOUT_SECONDS, settings.JOB_TIMEOUT_SECONDS))
    from app.services.ingestion_pipeline import ingest_document
    from app.services.parser import InvalidDocument

    try:
        ingest_document(doc_id, token)
    except InvalidDocument as exc:
        fail_job(doc_id, token, permanent=True, message=str(exc))
    except Exception as exc:
        # Exception type only: provider or parser exceptions may contain sensitive document text.
        log.error("ingestion_failed document_id=%s error_type=%s", doc_id, type(exc).__name__)
        fail_job(doc_id, token)


def serve():
    global stopping
    worker_id = uuid.uuid4().hex

    def stop(_signum, _frame):
        global stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        try:
            heartbeat(worker_id)
            job = claim_job()
            if not job:
                time.sleep(settings.WORKER_POLL_SECONDS)
                continue
            doc_id, token = job
            process = subprocess.Popen(
                [sys.executable, "-m", "app.worker", "--job", str(doc_id), str(token)],
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            )
            deadline = time.monotonic() + settings.JOB_TIMEOUT_SECONDS
            try:
                while process.poll() is None:
                    if stopping or time.monotonic() >= deadline:
                        process.kill()
                        process.wait()
                        fail_job(doc_id, token, message="Processing exceeded its time limit.")
                        break
                    heartbeat(worker_id)
                    time.sleep(min(2, settings.WORKER_POLL_SECONDS))
                if process.returncode:
                    fail_job(doc_id, token)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        except Exception as exc:
            log.error("worker_iteration_failed error_type=%s", type(exc).__name__)
            time.sleep(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", nargs=2)
    args = parser.parse_args()
    if args.job:
        run_child(*(uuid.UUID(value) for value in args.job))
    else:
        serve()
