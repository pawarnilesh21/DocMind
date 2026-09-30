# Share DocMind and prepare a panel demonstration

## 1. What goes to GitHub

The backend lives at the repository root in `app/`; the React frontend lives in `frontend/`. This is one Git repository, with a root `.gitignore` and a frontend `.gitignore`.

Keep these files and folders:

| Location | Purpose |
| --- | --- |
| `app/` | API, JWT authentication, database models, RAG pipeline and worker |
| `frontend/src/`, `frontend/public/` and frontend configuration | Browser application and build configuration |
| `alembic/`, `alembic.ini` | Database schema migrations |
| `requirements*.txt`, `requirements*.lock`, `frontend/package*.json` | Reproducible dependencies |
| `Dockerfile`, `compose*.yaml`, Docker ignore files | Container startup and isolated verification |
| `.env.example` | Placeholder settings; contains no working credentials |
| `tests/`, `frontend/tests/`, `.github/` | Automated tests and CI |
| `scripts/`, `evaluation/` example files | Setup, smoke checks and synthetic evaluation examples |
| `raw/evaluate_rag.py`, `raw/PRODUCTION_READINESS.md` | Optional evaluation and dated verification evidence |
| `README.md`, `OPERATIONS.md`, this guide | Setup, operations and presentation instructions |

Git ignores real `.env` files, Python environments, Node dependencies, built frontend files, caches, test reports, local databases, backups, old Chroma data and archived scratch scripts. Other files in `raw/` remain on your computer but are not uploaded. Do not force-add ignored files or share your whole working folder as a ZIP; use a clean Git clone or GitHub's source ZIP.

## 2. Upload when you are ready

Git is already initialized in this checkout. You do not need another `git init` or a separate repository inside `frontend/`.

Create an empty GitHub repository without an initial README, then run these commands from PowerShell. Replace `YOUR_USERNAME` with your actual GitHub username. Copy only commands, not the `PS C:\...>` prompt.

```powershell
cd C:\Users\nil55\AiEngineer\DocMind
git status --short
git add .
git diff --cached --stat
git diff --cached --name-only
```

Review the staged files. Real credentials, uploaded documents, databases and local-only raw scripts must not appear. `.env.example` is expected. Then:

```powershell
git commit -m "Prepare DocMind for sharing and demonstration"
git branch -M main
git remote -v
```

If there is no `origin`, add it:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/DocMind.git
```

If `origin` already exists, verify it points to the intended repository; do not add it twice or overwrite it blindly. Push when it is correct:

```powershell
git push -u origin main
```

Check the GitHub Actions results before handing over the project. No commit, remote change or push was performed as part of the folder cleanup.

## 3. Your friend's first run with Docker

Install Git and Docker Desktop, start Docker Desktop using Linux containers, and obtain working Gemini and Groq API keys. Internet access is required for initial downloads and AI requests. PostgreSQL is included in the Docker setup; a Neon account is not required.

```powershell
git clone https://github.com/YOUR_USERNAME/DocMind.git
cd DocMind
Copy-Item .env.example .env.local-review
notepad .env.local-review
```

Set `GEMINI_API_KEY`, `GROQ_API_KEY`, `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`. For each of the last two, generate a different random hexadecimal secret using this PowerShell block; paste the result into the relevant setting. Run it twice for two independent values:

```powershell
$secretBytes = New-Object byte[] 32
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$generator.GetBytes($secretBytes)
[System.BitConverter]::ToString($secretBytes).Replace('-', '').ToLowerInvariant()
$generator.Dispose()
```

Keep the remaining example settings for localhost. Do not send your private environment file to GitHub or use it in presentation screenshots.

```powershell
docker compose --env-file .env.local-review up --build -d
docker compose --env-file .env.local-review ps --all
```

Wait for the API and database to become healthy. The migration container exiting with code 0 is expected. Then create an account, replacing the sample email with your friend's email:

```powershell
docker compose --env-file .env.local-review exec api python -m app.admin create-user friend@example.com
```

Enter and confirm a password of 12–128 characters. Password typing is hidden. There is no default login. Open **http://localhost:8080** and sign in. Accounts and documents belong to this friend's local Docker database; your existing Neon or Docker data is not copied.

For later starts and stops:

```powershell
docker compose --env-file .env.local-review up -d
docker compose --env-file .env.local-review stop
```

Do not remove database volumes when you want to keep the demo data.

For errors:

```powershell
docker compose --env-file .env.local-review logs --tail=100 migrate api worker web
```

Run Compose from the project root, not `frontend/`. Use port 8080 with Docker. Port 5173 belongs to the separate direct-development setup documented in the root README. If the AI provider rejects a model or quota, inspect provider availability/settings before the demonstration; Docker alone does not guarantee provider access.

## 4. A five-minute panel demonstration

1. Explain the problem: finding supported answers in a user's documents while retaining inspectable sources.
2. Sign in and upload `evaluation/synthetic-document.txt`. This is synthetic demo content, not private user data.
3. Show queued/processing/ready states. Explain that the API accepts the upload and a separate worker processes it through shared PostgreSQL jobs.
4. Ask a factual question whose answer appears in the uploaded file. Inspect the returned citation and supporting source. TXT citations use chunk references; PDF citations preserve available page numbers.
5. Request a summary of that same document. Summarization accepts one ready document within its configured size limit.
6. Ask a question clearly not answered by the document. Explain the intended abstention behavior and that evidence verification is a safeguard, not proof of perfect accuracy.
7. Show logout and explain how the database revokes the JWT session. Finish with tests, limitations and future work.

Rehearse the complete flow with the exact demo file and live provider account before presentation day. Keep a preprocessed document and your own rehearsal screenshots available in case the network or provider is unavailable.

## 5. Current architecture to explain

**Upload:** React → FastAPI → PostgreSQL queued job → worker parses/chunks → Gemini embeddings → atomic storage of chunks, vectors and ready status.

**Question:** authenticated request → owner-filtered pgvector cosine retrieval → Groq structured claims and evidence → exact-quote/citation validation → separate entailment check → answer with citations or abstention.

**Authentication:** HS256 JWT in an HttpOnly cookie, expiry/issuer/audience validation, CSRF protection and database-backed revocation. Passwords use Argon2id. JWT sessions are not fully stateless and do not implement automatic refresh.

**Current stack:** Python, FastAPI, PostgreSQL/pgvector, Gemini/Groq APIs, React and Docker. LangChain and ChromaDB describe an earlier prototype, not the current runtime.

**Why two backend processes?** The API remains responsive while a worker handles slow document processing. Leases, bounded retries and stale-worker checks support recovery after interruptions.

## 6. Evidence and honest limits

The latest recorded JWT-update run passed 52 tests, skipped 3 PostgreSQL-specific tests, and measured 77% backend coverage. Earlier PostgreSQL, browser and Docker checks are separately dated in `raw/PRODUCTION_READINESS.md`; do not present those as a fresh test of the JWT release. Browser checks use mocked API responses. Coverage is code coverage, not answer accuracy.

The project has not been publicly deployed or load-tested for a claimed production scale. Representative RAG evaluation, deployment configuration and backup restoration remain release checks. Scanned PDFs require external OCR; public signup, SSO and billing are not implemented. Accounts are created by the operator command.

The old interview guide in the local-only archive is historical and contains obsolete architecture details. Use this guide and the current source code for the panel.
