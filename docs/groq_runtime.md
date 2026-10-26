# Opt-in Groq JD application — 26 October 2026

## Implemented and verified boundary

The existing Groq interpreter, LangGraph JD generation, company-policy retrieval,
authenticated recruiter API and PostgreSQL persistence work together in a separate
Docker Compose project. No application AI algorithm or authentication rule changed.
`compose.yaml` remains the provider-disabled baseline. `compose.groq.yaml` is an
explicit opt-in override; the backend receives outbound networking while PostgreSQL
stays on the internal network without a published port. This bridge is not a
domain-level outbound firewall.

The owner confirmed free-plan availability, remaining quota and no paid billing
before inference. One synthetic recruiter-chat request performed real Groq
interpretation and generation, with SDK retries disabled. It returned HTTP 200,
one saved Backend Engineer job, a server-generated Job Reference and revision 1.
Two policy grounding citations were returned. The policy is fictional demo policy,
embedded with real local BGE; neither policy vectors nor AI responses were mocked.
This proves this small JD workflow, not model accuracy, throughput, CV screening,
full BID acceptance or future free-tier availability.

Fresh authenticated HTTP retrieval and browser refresh/retrieval passed. The
browser displayed the persisted draft and carried the same job into Candidate
Screening. Groq is the first available provider option; selection remains explicit.
Its external-processing checkbox starts unchecked. A request without that consent
was rejected before inference. No screening request or second model request was
made during the browser checks. Saved-conversation responses omit null fields;
comparison with the generation response must account for that serialization rule.

## Current office runtime

Application: <http://groq-20261026.localhost:5280/>. Use that hostname consistently
so its authentication cookies remain separate from previous loopback demos.
The frontend, FastAPI and PostgreSQL run in containers. Only frontend port 5280
is published, on loopback. The database is newly created and migrated explicitly
to `0017_booked_interview_email`; no preserved database was reused or changed.

From this worktree root, the repeatable startup command for the already prepared
runtime is:

```powershell
docker compose --env-file data/groq-runtime-20261026/compose.env -f compose.yaml -f compose.groq.yaml up -d --no-build --wait --wait-timeout 120
```

This starts the built, configured application; it does not migrate, seed policy,
provision accounts or call Groq. Keep its existing project configuration and volumes.
Do not rerun first-time provisioning against it. Synthetic credentials are in the
ignored, owner-restricted `data/groq-runtime-20261026/LOGIN.json`, not in Git or this
document. Private acceptance results and synthetic screenshots are in that same
directory. The runtime is left running; no automatic shutdown is configured.

Sign in, use Home's saved job **Refine saved JD**, or select its saved conversation
in JD Assistant. To generate another draft, first check free quota, select Groq,
review the external-processing disclosure and explicitly consent. Do not repeatedly
resubmit a failed or uncertain request.

## First-time prerequisites on another machine

1. Follow [Docker startup isolation checks](docker_startup.md). Choose an unused
   port, fresh Compose project and fresh volumes. Never import an old database URL.
2. Use Python with the pinned backend `python-dotenv` dependency and a complete,
   already available `BAAI/bge-small-en-v1.5` Hugging Face cache. The helper requires
   config, tokenizer, SentenceTransformers modules and model weights together.
   It does not download models. Credentials and model assets are machine-local.
3. Run `python docker/configure_groq.py --source-env <private-source-file>` once,
   adding `--bge-cache <existing-model-cache>` and `--port <unused-port>` if needed.
   The helper refuses an existing destination and copies only `GROQ_API_KEY` and
   `LLM_MODEL`. It creates a separate random database password/project and restricts
   its ignored directory to the owner. Never print resolved Compose configuration.
   On this office machine the supplied sibling `TalentTrace-AI.env` was absent;
   the actual existing source was the original checkout's `.env`. Its database URL,
   old policy identity and AssemblyAI key were not imported. The original was not
   edited.
4. Build the two application images with the same `--env-file` and `-f` arguments:
   `docker compose ... build`. The default remains the pinned standard backend
   Dockerfile. Clean-machine dependency installation can require substantial disk,
   time and network access; this task does not establish clean-machine acceptance.
5. Start only the new database (`docker compose ... up -d --wait db`). Verify its
   project/volume ownership, database and role, and empty application schema before
   explicitly running `docker compose ... run --rm --no-deps backend python -m
   alembic upgrade head`. Verify the single current migration head. Never migrate a
   preserved deployment as an incidental startup action.
6. With that new database only, run `docker compose ... run --rm --no-deps backend
   python -m app.rag.seed_demo_policy`. The cached model is mounted read-only;
   Hugging Face offline settings remain enabled. Save the resulting synthetic
   policy document identity privately as `COMPANY_POLICY_DOCUMENT_ID` in the
   generated `groq.env`. Do not reuse a document identity from another database.
7. Explicitly provision a fictional recruiter using the existing administrative
   `python -m app.db.provision_recruiter` command in that backend environment.
   Then use the startup command above and verify all three health checks.

The ellipsis in first-time examples means the same private `--env-file` and two
Compose files; it is not a literal runnable argument. No automatic first-time
database setup or model download is hidden in `up`.

## Reusing verified office dependencies

An initial standard build began an unnecessary repeat PyTorch download and was
cancelled. The existing cached backend image was then inspected offline: all 20
pinned backend requirements and CPU PyTorch matched. Only after that verification,
an additional local dependency-image tag was made and the private Compose file
selected `docker/backend_cached.Dockerfile` plus that image through
`TALENTTRACE_GROQ_DOCKERFILE` and `TALENTTRACE_BACKEND_DEPENDENCY_IMAGE`.
The optional Dockerfile replaces the old application/migration sources inside the
new image with current source, retaining the verified packages and non-root user.
It does not edit the original image, worktree or running environment. Frontend
dependencies were reused and a new production frontend was built.

These optional private overrides are office-specific. Do not copy them to another
machine or assume a similarly named image matches requirements. Reverify every
pinned package and CPU PyTorch before using this acceleration after dependency
changes. Dependency-image identity is retained privately. No model weights or
configuration files enter either build context.

## Safety and validation

LiveKit credentials, AssemblyAI, Ollama, caption/transcript storage, F11,
interview email, publishing and biometric processing remain absent/disabled.
No Cloud, STT, email, publishing or CV processing was exercised. Existing CORS,
HttpOnly/SameSite cookies, mutation protection and recruiter/job ownership remain
in force. Do not expose this development HTTP origin publicly.

Validated in this increment:

- Three offline configuration tests: credential allowlist/no overwrite, complete
  cached-model prerequisite, and resolved Compose isolation/disabled features.
- 141 focused backend tests for AI selection, recruiter chat and record ownership/
  persistence; 4 frontend provider/consent tests. All passed, none skipped.
- Containerized frontend TypeScript and production Vite build passed; the existing
  large LiveInterviewPage chunk warning remains unrelated to this JD workflow.
- Real authenticated provider readiness, rejected missing consent, real Groq JD
  generation, fresh-session persistence, browser restoration after refresh and
  same-job screening navigation passed.

No source changes were needed in the existing Groq application. AssemblyAI and
the other historical credentials remain untouched and unused. Free-tier quota
and key validity must be rechecked if a later request fails; do not assume this
single successful request guarantees future availability.
