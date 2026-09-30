# DocMind

A private RAG application for PDF, DOCX, and UTF-8 text documents. Each account has its own documents and conversations. Uploads are durably queued, processed in a separate worker, and indexed in PostgreSQL with pgvector. Answers include validated source excerpts and a separate grounding check.

**Status:** implemented and locally verified for review. No public deployment has been performed. See [verification results](raw/PRODUCTION_READINESS.md) for evidence, supported limits, and deployment acceptance checks.

Sharing with a friend or preparing a panel demo? Start with [SHARING_GUIDE.md](SHARING_GUIDE.md) for GitHub upload, clean setup, a demonstration script, and the current architecture. Optional evaluation tooling and archived development notes live in [raw](raw/README.md); old experiments are excluded from Git.

## Local review with Docker

Requirements: Docker Desktop or Docker Engine with Compose, and working Gemini and Groq API keys.

1. Copy `.env.example` to `.env.local-review`.
2. Set `POSTGRES_PASSWORD` to a long random hexadecimal password, set `JWT_SECRET_KEY` to a random secret of at least 32 bytes, and fill the two API keys. Keep the example development origin and host settings for localhost.
3. From the project root:

```sh
docker compose --env-file .env.local-review up --build -d
docker compose --env-file .env.local-review exec api python -m app.admin create-user you@example.com
```

The account command prompts for a password; it is not stored in shell history. Open **http://localhost:8080**, sign in, upload a document, wait for `ready`, and create a chat.

This creates a new Docker database volume. It does **not** use the database URL in your existing `.env`, import existing data, or expose PostgreSQL/API ports to the host.

```sh
docker compose --env-file .env.local-review logs --tail=100 api worker
docker compose --env-file .env.local-review stop
```

Do not add `--volumes` when stopping/removing a stack whose data you want to keep.

## Development without containers

Use Python 3.11 and Node.js 24. The old `venv` has incompatible packages; use a fresh environment.

```sh
python -m venv .venv-prod
# Activate .venv-prod for your shell.
python -m pip install --require-hashes -r requirements-dev.lock
```

Set `DATABASE_URL` to a PostgreSQL database with pgvector available. Set provider keys and allowed localhost origins in `.env`. Back up existing data before applying migrations.

Before starting an existing checkout, run `python -m scripts.prepare_jwt` to add a generated signing key to existing `.env` and `.env.local-review` files. Existing keys are preserved and secrets are not printed. Production deployments must supply `JWT_SECRET_KEY` through a secret manager and share the same key across API replicas.

```sh
alembic upgrade head
python -m app.admin create-user you@example.com
uvicorn app.main:app --host 127.0.0.1 --port 8000
# In another terminal:
python -m app.worker
# In frontend/:
npm ci
npm run dev
```

Open http://localhost:5173. The development API documentation is at http://127.0.0.1:8000/docs.

## Verification

Offline tests never load your database or call real AI providers:

```sh
python -m pytest
ruff check app tests
ruff format --check app tests
python -m pip check
```

For the real PostgreSQL integration tests:

```sh
docker compose -p docmind-verification -f compose.test.yaml up -d --wait
# PowerShell:
$env:TEST_DATABASE_URL = 'postgresql://docmind_test:local-test-only@127.0.0.1:55432/docmind_test'
python -m pytest --cov=app --cov-report=term-missing
# Bash: export TEST_DATABASE_URL=postgresql://docmind_test:local-test-only@127.0.0.1:55432/docmind_test
```

The test harness only permits the local database named exactly `docmind_test`. It clears that database between tests. Never point it at user data.

Browser checks (API responses mocked; real Chromium and production frontend build):

```sh
cd frontend
npm ci
npm run lint -- --deny-warnings
npm run build
npx playwright install chromium
npx playwright test
npm audit --audit-level=high
```

Full local container smoke (run after backend tests; the worker must not run concurrently with tests that clear their database):

```sh
docker build -t docmind-api:verification .
docker build -t docmind-web:verification frontend
docker compose -p docmind-verification -f compose.test.yaml --profile smoke up -d --wait
python -m scripts.smoke_local
docker compose -p docmind-verification -f compose.test.yaml --profile smoke down
```

The smoke stack has ephemeral test storage. It uses synthetic data and does not call paid AI APIs.

Optional live provider check, using a small synthetic document and your configured keys:

```sh
python -m scripts.check_providers
```

This incurs a few embedding and inference requests. It does not send your stored documents.

## Architecture and behavior

- FastAPI API and React frontend; same-origin session cookies in deployment.
- Argon2id password hashes, HttpOnly cookies, CSRF tokens, and explicit origin/host validation.
- Authentication now uses HS256-signed JWT session cookies, with expiry, issuer, audience and required-claim validation. PostgreSQL session records preserve immediate logout and password-reset revocation; this is not stateless authentication. JWTs are never stored in browser localStorage.
- Account creation, password reset, disabling accounts, and legacy adoption use the operator CLI. Public registration is deliberately disabled.
- Every document, conversation, history, citation lookup, and retrieval query is scoped to its owner.
- PostgreSQL stores original uploads, extracted chunks, vectors, job leases, sessions, and rate limits. Source text and vectors become visible in one transaction.
- Worker jobs use bounded child processes, hard timeouts, retry limits, and lease tokens. Expired work is reclaimed after crashes; stale jobs cannot overwrite newer work.
- Retrieval uses normalized 768-dimensional Gemini embeddings, separate document/query tasks, and exact cosine search. The model identifier is stored with each vector.
- Answers use claim-level structured output, exact supporting quotations, valid source identifiers, and an additional entailment check. Invalid evidence causes abstention. AI verification can still make mistakes.
- Chat writes are idempotent through `request_id`; simultaneous generation in the same conversation receives 409. Provider failure does not save a partial turn.
- Deleting a document atomically deletes its original bytes, chunks, and vectors. Historical chat messages remain until their conversation is deleted.
- PDF citations preserve physical PDF page numbers. DOCX/TXT and legacy chunks use chunk citations when page numbers are unavailable.
- Summary mode requires one ready document and supplies all its chunks within the documented summary limit.

## Supported limits

Defaults: 20 MB uploads, 300 PDF pages, 500,000 extracted characters, 750 chunks, and 100 documents per account. A question is limited to 4,000 characters and up to 20 selected documents. Summaries accept up to 36,000 chunk characters and reject longer inputs explicitly.

Per-account limits: 20 uploads/retries per hour, 10 chat requests per minute, and 200 per day. Login throttles apply to both IP and account. Limits are shared through PostgreSQL.

Scanned PDFs require external OCR before upload. DOCX paragraphs and tables are supported; text embedded in images, headers, footnotes, or complex layout is not promised. There is no public signup, billing, SSO, OCR service, or agent/tool execution.

## Existing data

The additive migration preserves legacy rows and marks documents `legacy`. Existing unowned data is invisible to all accounts until an operator explicitly adopts it:

```sh
python -m app.admin claim-legacy you@example.com --confirm
```

This assigns **all unowned documents and conversations** to that account and queues reindexing. Review the ownership decision first. Legacy documents lack original file bytes; their existing extracted chunks are embedded again, with page numbers remaining unavailable where the original parser discarded them.

The old `chroma_data` directory is not read or deleted. Retain its backup until migration is verified, then follow your data-retention procedure. It may still contain historical document text.

Changing `EMBEDDING_MODEL` requires reindexing:

```sh
python -m app.admin reindex you@example.com --confirm
```

Embeddings must support 768 output dimensions. Review and reindex intentionally; mixing incompatible embeddings is prohibited.

## Operator procedures

```sh
python -m app.admin reset-password you@example.com
python -m app.admin disable-user you@example.com
```

Password resets revoke existing sessions. Disablement immediately prevents subsequent authenticated requests.

`/health` checks process liveness. `/ready` checks the schema revision, pgvector operation, database connectivity, and a recent worker heartbeat. It does not call providers on every probe. Logs include request IDs, route templates, status, and duration; they omit request bodies and provider secrets.

See [OPERATIONS.md](OPERATIONS.md) for backups, restore verification, and deployment preparation.
