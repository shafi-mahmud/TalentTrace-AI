# Recruiter-owned jobs and shared screening review

## Implemented in code

Administrator-provisioned email/password accounts gate the recruiter workspace.
There is no public registration. Passwords use salted scrypt (`N=2^17`, `r=8`,
`p=1`); only hashes are stored. Login returns an opaque, revocable eight-hour
HttpOnly/SameSite=Strict session cookie. The database stores its SHA-256 hash,
not the bearer token. Outside `ENVIRONMENT=development`, cookies require HTTPS.
Mutation requests require `X-TalentTrace-Request: 1`; browser origins must match
the configured trusted CORS origins or the request host. Never add wildcard or
untrusted origins. API responses use `Cache-Control: no-store`.

Login failures use fixed public messages. A bounded process-local IP throttle
limits password work; deployment-wide rate limiting, MFA, password recovery,
administrator UI, security audit records and account lifecycle automation remain
**Planned**. The administrator provisions accounts through an interactive local
command; passwords must never be supplied in shell arguments or committed.

Migration `0002_recruiter_jobs` adds recruiter accounts, hashed sessions,
owner-scoped conversations, successful chat turns and job profiles. Existing
knowledge tables, policy data and Screening checkpoint schemas are unchanged.
Conversation state uses bounded, validated JSON, not pickle. Successful chat
responses, state and job updates commit together; a provider failure does not
save a partially completed turn. Existing conversations are locked during turns.
The prior 20-turn/12,000-character bounds and 30-minute idle expiry remain.
History remains readable after expiry, but further messages require a new chat.
No automatic deletion/retention job is implemented.

After JD generation, one saved job becomes active in both workspaces. There is
no transfer button or separate criteria review in the JD card. Candidate
Screening is the single editor: edit criteria, choose must-have/preferred, then
**Confirm requirements**. A manual job can be created there without a JD.
References are backend-generated `TT-JOB-*` values derived from stored job UUIDs;
the LLM and browser cannot assign them. Saved jobs/history can be restored after
reload. An account-specific session-storage pointer remembers only the active job
UUID; its contents and approval are reloaded from the owner-checked API. New chat
clears that pointer. Late reload responses cannot overwrite newer criteria edits. Criteria edits clear local approval/results; confirmation stores an exact
snapshot using an optimistic revision check. Regenerating a JD clears saved
approval. Reloading saved requirements explicitly discards unsaved edits.

The screening API requires that exact saved approved snapshot and an owned job.
Existing graph, hard decisions, evidence checks, overall coverage and ranking are
reused unchanged. CV files use recruiter-specific subdirectories below the private
upload root; every upload/extract/OCR/profile/screening request checks ownership.
Old shared-root uploads are not adopted automatically. Switching jobs preserves
the selected batch but rejects mismatched references. Selected batches, extracted
profiles and screening results remain browser-memory state; candidate/application
and result persistence are **Planned**.

Publication requires a saved owned generated draft and matching draft content.
The backend supplies the saved job reference and still invokes the existing MCP
path. Formal JD approval, publication audit and deduplication are **Planned**;
an unconfirmed external publication must not be retried automatically.

## Conservative synthetic-policy suggestions

Recruiter requirements remain the primary source of criteria. For a role mentioning
security/privacy duties, two curated practices may be suggested: applying access
controls and reporting incidents. Both start **preferred**, requiring recruiter
review before screening. Each retains the retrieved excerpt, source title and
citation ID. The mapping pins the repository's approved synthetic policy UUID,
version and normalized content SHA-256; unrelated, modified or unavailable policy
context yields no policy suggestions. No protected traits, general fairness prose,
work hours or contractual terms become screening requirements.

These are explicitly synthetic demo suggestions, not automatic rule extraction
from arbitrary policies. Source excerpts establish origin, not semantic correctness
or continued support for recruiter-edited descriptions. Production approved-policy
selection, ingestion and criterion governance remain **Planned**.

## Setup for the intended demo database after review

Preserve the existing PostgreSQL/pgvector database and configured policy document.
With the normal local environment configured, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.provision_recruiter
```

Provision a synthetic recruiter account using the hidden password prompts, then
restart the intended backend only with owner authorization. Use the existing
frontend proxy and consistent browser hostname for same-site cookies. Outside
development, serve HTTPS. The preserved demo database was not migrated or reseeded. Verification used
isolated databases and synthetic accounts; apply these commands to the intended
demo database only after integration review.

## Verification limits

Automated tests exercise real auth/ownership/router logic with a transactional
database double, mocked providers and no real publication. They cover cookie
expiry/revocation, CSRF, foreign resources, bounded login input, private CV roots,
conversation restoration/rollback, saved approval and publication guards. Offline
Alembic SQL verifies the new tables/FKs and that downgrade leaves knowledge tables
alone. Frontend API/state/rendering tests cover saved-job validation, shared review,
confirmation invalidation, synthetic provenance and session transport.

## Isolated integration verification - 09 Oct 2026

**Verified:** Docker Desktop and the preserved PostgreSQL container were started
without deleting volumes. The preserved demo policy was available; that database
remained at migration 0001. Separate synthetic verification databases passed
clean-schema upgrade to head, version-0001 upgrade, downgrade to 0001 and re-upgrade.
Administrator provisioning stored scrypt hashes. Real HTTP/PostgreSQL checks passed
login failure/success, cookie settings, CSRF, expiry/logout, persisted conversations,
jobs, snapshots and two-recruiter isolation. Foreign jobs, chat, CV upload,
extraction, OCR, profile extraction, screening and publication were denied.

Authenticated browser checks used localhost frontend 5176/backend 8003: generated
and restored a job, shared it automatically with Candidate Screening, confirmed
Must-have/Preferred criteria, uploaded a synthetic PDF and screened it. A material
revision invalidated approval while retaining the batch; reconfirmation worked.
Active-job reload, manual setup and synthetic policy labels were checked separately.

**Verification boundary:** SQLAlchemy transactions, migrations, authentication,
PDF extraction, pgvector queries and existing graphs were real. Interpreter,
generation, profile extraction, semantic matching and embedding outputs used
synthetic fixtures in a temporary runtime outside the repository. No live Groq,
BGE inference or Discord publication was performed for this increment. This does
not establish production readiness or post-authentication real-provider behavior.

The opt-in `tests/test_recruiter_ownership_live.py` requires an explicitly isolated
localhost fixture runtime and `TALENTTRACE_OWNERSHIP_VERIFY_URL` /
`TALENTTRACE_OWNERSHIP_VERIFY_DATABASE`; ordinary suites skip it. Its setup is not
an application authentication bypass. Keep verification credentials, uploads and
runtime configuration outside Git. Use synthetic data until deployment, access,
consent, encryption/backups and retention controls are reviewed.
