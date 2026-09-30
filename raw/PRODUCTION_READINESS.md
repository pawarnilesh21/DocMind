# Development verification

Review date: 2026-09-14.

The code has been hardened and is ready for the user's local acceptance review within the documented product limits. It has not been publicly deployed or certified for an unspecified production workload.

## Implemented

- Private operator-provisioned accounts, Argon2id passwords, signed JWT cookies backed by revocable database sessions, CSRF and origin protection.
- Owner isolation for document APIs, conversations, history, citations, and SQL vector retrieval.
- Patched dependencies and hashed, universal Python lock files; frontend package lock.
- Transactional PostgreSQL/pgvector storage replacing the separate Chroma index.
- Durable ingestion, subprocess resource limits, deadlines, bounded retries, crash recovery, and stale-worker protection.
- Bounded uploads before parsing, authenticated upload admission, account quotas, shared rate limits, and pagination.
- Correct summary routing and source lookup; PDF page preservation and DOCX table extraction.
- Structured claims, exact quotation validation, cited-source validation, an entailment pass, and safe abstention.
- Chat idempotency, concurrent-request exclusion, and post-generation source revalidation.
- Non-root containers, same-origin reverse proxy, CSP, validated configuration, liveness/readiness, request IDs, and CI.
- Local-review instructions, migration ownership procedures, and backup/restore runbook.

## Completed checks

- 38 backend tests passed against the isolated PostgreSQL/pgvector database.
- Backend coverage: 78% on the measured 38-test run. Untested lines include operator CLI and worker supervisor branches; coverage is not a security certification.
- Three Chromium browser tests passed: sign-in/out, summary submission and citation inspection, and mobile validation.
- Python lint and formatting checks passed; frontend lint/build passed.
- Both Linux Docker images built successfully from lock files.
- Full Docker smoke passed: frontend CSP, readiness, login, CSRF, Q&A abstention, real worker subprocess failure handling, deletion, and logout.
- Runtime dependency audit: no known vulnerabilities reported.
- Frontend npm audit: zero reported vulnerabilities.
- Live Gemini/Groq check passed using synthetic text: document/query embeddings, 768 dimensions, cosine similarity 0.842, structured answer, exact citation, and grounding verification.
- The unavailable previous Groq default was replaced with qwen/qwen3.8-27b after checking the account's model inventory.

Original user documents, the configured existing database, and the old Chroma directory were not modified or migrated during verification.

## Acceptance before deployment

JWT authentication update (2026-09-29): 52 tests passed and 3 PostgreSQL-specific tests were skipped on the isolated SQLite run, with 77% backend coverage. JWT cases cover signature/algorithm rejection, expiry, issuer/audience, required claims, subject binding, legacy-cookie rejection, logout/relogin revocation and disabled accounts. Lint, formatting and installed dependency consistency checks passed. Docker/PostgreSQL integration checks were not rerun for this update; the earlier results above are historical. Local signing keys were generated without exposing their values. Restart/rebuild services and sign in again after upgrading.

The user requested development and personal review before deployment. Remaining release decisions are hosting, TLS/domain setup, deployment secrets, operational alerts, backup retention/restore drill, realistic load targets, and RAG evaluation against the user's representative documents.

The small live provider check verifies API compatibility, not a statistically meaningful quality benchmark. The supplied evaluation command counts empty retrieval and failed cases, so they cannot disappear from the result.

No source files were committed or pushed. Git originally tracked only README.md; review and commit the application, lock files, migrations, tests, and CI configuration before a release.
