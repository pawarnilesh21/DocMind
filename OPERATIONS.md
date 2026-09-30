# Operations and release preparation

No hosting provider has been selected. The supplied Compose stack is for local review. Select hosting, TLS, backups, monitoring, capacity targets, and operational ownership before an internet-facing release.

## Environment

JWT sessions require `JWT_SECRET_KEY` (a cryptographically random secret of at least 32 bytes), with `JWT_ISSUER=docmind` and `JWT_AUDIENCE=docmind-web` by default. Share the signing key across API replicas using your secret manager. Rotating the key immediately invalidates current JWTs; coordinate restarts and require users to sign in again. JWT lifetime follows `SESSION_HOURS` (12 by default); there is no automatic refresh endpoint. Database session records still enforce revocation. The upgrade rejects previous opaque session cookies and requires a fresh login, with no database schema migration needed for the authentication change.

For production set ENVIRONMENT=production, DEBUG=false, COOKIE_SECURE=true, explicit HTTPS ALLOWED_ORIGINS, and explicit ALLOWED_HOSTS. Invalid combinations fail configuration validation. Use your deployment secret manager; never commit .env files.

Put the frontend behind a TLS-terminating proxy. Only the frontend should be reachable from outside the private application network. PostgreSQL, the API, worker, and migration service must remain private. The supplied Uvicorn configuration trusts forwarded headers because the API is private behind the bundled proxy; do not expose its port directly.

The frontend serves a strict Content Security Policy and locally hosted assets. API request bodies, provider outputs, credentials, and uploaded text must not be sent to access-log collectors. Configure edge access logs to exclude sensitive query parameters.

Provider keys need account-level spend limits and alerts. The application has per-user request and input bounds; request counts do not replace monetary limits.

## Release sequence

1. Run CI, the real PostgreSQL tests, browser tests, and both container builds.
2. Run the live synthetic provider check and evaluate RAG quality on representative documents.
3. Build immutable images; record their digests and lock-file revision. Pin base-image digests for your approved deployment release.
4. Take a backup and verify that it can be restored before changing an existing schema.
5. Run one migration service using a migration role with extension/schema permissions. Use a narrower runtime database role in hosted environments.
6. Start workers and API; wait for /ready. Start the frontend.
7. Verify login, upload, processing, Q&A, source inspection, summary, logout, and deletion using a non-sensitive test document.
8. Confirm TLS, cookie flags, authorized origins, readiness monitoring, error alerts, job failures, provider budgets, and database capacity.

There is no automatic destructive downgrade. Restoring a known backup and previous image is the rollback procedure for this migration. Migrations preserve old records but quarantine their ownership.

## Backup and restore

PostgreSQL contains the complete new application state, including original files and embeddings. Use provider-managed encrypted backups/PITR where available. Keep encrypted off-site backups with a defined retention period and access policy.

For the local Compose stack, use pg_dump's custom format inside the container and docker cp; avoid PowerShell binary-output redirection.

```sh
docker compose --env-file .env.local-review exec db pg_dump -U docmind -d docmind -Fc -f /tmp/docmind.backup
docker compose --env-file .env.local-review cp db:/tmp/docmind.backup ./docmind.backup
```

The backup contains private text, uploaded files, account password hashes, and session records. Store it accordingly. Never commit it.

Restore into a separate empty database with pgvector installed, using pg_restore --no-owner --no-acl and the intended database role. Check migration revision, account access, document counts, source text, vector dimensions, and a known retrieval query. Revoke restored sessions before bringing a restored service online. Record the restore duration and compare it to the recovery target.

The local smoke database uses tmpfs and is intentionally disposable. It is never a backup location.

## Monitoring and failure handling

- Alert on repeated /ready failures, elevated 5xx or p95 latency, repeated worker restarts, queued-job age, failed jobs, storage growth, and provider quota/spend.
- Correlate errors through X-Request-ID. Route logs omit document and conversation identifiers.
- Inspect worker logs for document ID and error type; the UI exposes a safe processing error.
- Retry failed documents through the UI after fixing the cause. Retries count toward upload quota.
- Provider outages return a recoverable 503. The frontend retains the submitted question and reuses its request ID on a retry.
- PostgreSQL rate buckets and expired sessions are cleaned by the worker. Worker availability is part of readiness.
- Increase worker concurrency only after testing database capacity, account quotas, parser memory use, and provider limits.
- Exact vector search is appropriate for the bounded initial deployment. Measure realistic document counts and concurrent queries before choosing an approximate index; tenant filtering must remain enforced.

## Retention and deletion

Document deletion removes that document's original bytes, text chunks, and vectors in one transaction. It does not erase previously generated chat answers or backup copies. Delete conversations separately and apply your backup retention policy.

Legacy Chroma files are outside the new database. They remain untouched to avoid data loss; account for them explicitly in migration verification and retention.

## Known product limits

OCR, SSO, public signup, billing, agent tools, arbitrary-file ingestion, and unlimited document summarization are outside the implemented scope. The UI rejects oversized summaries instead of silently omitting content. AI evidence and entailment checks reduce error risk but do not certify factual correctness.

Set availability, latency, user-count, storage, recovery, and quality targets before making a production-readiness claim for a specific deployment.
