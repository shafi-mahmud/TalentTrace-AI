# PostgreSQL checkpoint foundation — Redmine #647112

## Implemented

The official `AsyncPostgresSaver` provides persistent LangGraph state through
`backend/app/db/checkpointer.py`. Use the same PostgreSQL instance but a
**separate database**, such as `talenttrace_checkpoints`. SQLAlchemy application
records and RAG tables stay in the business database. LangGraph owns its
`checkpoint_migrations`, `checkpoints`, `checkpoint_blobs` and
`checkpoint_writes` tables; TalentTrace Alembic must not manage these tables.
There are no checkpoint ORM models or custom schema/search_path configuration.

The infrastructure branch starts from `develop`'s earlier database foundation.
JD/RAG implementation on `feature/job-description-agent` is not copied or merged
into this task. This foundation does **not** checkpoint the existing JD workflow.

## Configuration and explicit setup

Provision the checkpoint database externally on the existing PostgreSQL
instance. The application does not create databases.

**Example — safe placeholders only:**

```text
DATABASE_URL=postgresql+asyncpg://application:replace_me@localhost:5432/talenttrace
LANGGRAPH_CHECKPOINT_DATABASE_URL=postgresql://checkpoints:replace_me@localhost:5432/talenttrace_checkpoints?connect_timeout=10
```

The checkpoint URL is a `SecretStr`, optional at import/startup. It must be a
valid `postgresql://` Psycopg URL with an explicit database; asyncpg URLs and
indirect service configuration are rejected. Configuration also rejects the
configured business database name, including a query-parameter override. Use
different database credentials with least privilege where deployment permits.
Missing configuration fails only when checkpoint functionality is invoked.
The CLI never edits `.env`, prints URLs/credentials or logs checkpoint payloads.

After provisioning, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.db.setup_checkpointer
```

This explicitly calls `await saver.setup()` and closes the connection. Setup
uses LangGraph's own migrations and can be rerun to apply them. Run it with an
appropriately privileged setup identity; runtime identities should have narrower
permissions. Neither FastAPI import/startup nor health checks run setup or connect.

Future workflows can keep `async with open_checkpointer() as saver:` open for
their entire graph execution and compile with `checkpointer=saver`. Each context
owns one connection and closes it, including when the caller raises an error.
Opening the connection has a 15-second application deadline; the example also
sets libpq's explicit connection timeout so failed endpoints cannot wait indefinitely.
No implicit setup or in-memory fallback occurs. Connection/setup failures have
sanitized infrastructure errors; caller workflow errors keep their own semantics.

On Windows, Psycopg async execution needs a compatible selector event loop.
The setup CLI and live proof helper explicitly use `asyncio.SelectorEventLoop`
through `asyncio.run(..., loop_factory=...)`, tested with Python 3.12. Future
FastAPI integration must preserve this compatibility rather than changing the
global event-loop policy on import. This task adds no application connection pool.

## Stable identifiers and serialization

`WorkflowThread` validates exactly `jd`, `screening`, `copilot` and `evaluation`
as identifier namespaces, paired with an opaque UUID. Its canonical string is
`<workflow-kind>:<uuid>`; persist and reuse that identifier to resume a run.
Parsing rejects unknown namespaces, noncanonical/malformed IDs and PII-like
strings. Namespaces do not implement business workflows or ownership checks.

The saver uses `JsonPlusSerializer(allowed_msgpack_modules=None,
allowed_json_modules=None, pickle_fallback=False)`. This restricts reconstruction
to the library's built-in safe types; it does not enable arbitrary modules or
pickle fallback. The persistence proof uses primitive synthetic state only.
Future custom state types need deliberate review/allowlisting, not permissive
deserialization. Library-supported LangGraph internal types remain necessary.

Checkpoint data will be privacy-sensitive: protect database access, use
backend-only credentials, avoid payload logging, and enforce future application
authorization for thread access. Storage/database encryption, backups and secure
transport are deployment responsibilities. Retention/deletion rules and business
workflow authorization are not implemented here.

## Reproducible restart/resume proof

`backend/tests/checkpoint_resume_worker.py` is a test-only graph:
`START -> prepare -> human_pause -> finish -> END`, using `interrupt()`.
With the checkpoint URL configured for the process and setup already applied,
invoke it from `backend/` twice with the same new opaque thread ID:

```text
python tests/checkpoint_resume_worker.py pause jd:<new-synthetic-uuid>
python tests/checkpoint_resume_worker.py resume jd:<same-synthetic-uuid>
```

Process 1 verifies the persisted prepared state and pending interrupt, then exits
and closes its connection. Process 2 reads that snapshot through a new saver and
resumes with `Command(resume=True)` to the expected final primitive state. No
MemorySaver, shared Python state, disk checkpoint files, Groq, BGE or business JD
graph are used. Output contains operational status and process ID only.

## Implemented and verified — 07 Oct 2026

- Dependency resolution and `pip check` passed with `langgraph==1.2.13`,
  `langgraph-checkpoint-postgres==3.1.2`, `psycopg[binary]==3.3.6` and the
  installed checkpoint core 4.2.0, on Windows/Python 3.12.
- 35 focused checkpoint tests and all 50 backend tests on this infrastructure
  branch passed. This count reflects its `develop` baseline, not the larger
  JD/RAG feature-branch suite.
- The preserved local PostgreSQL 17.11 instance provisioned/reused the separate
  `talenttrace_checkpoints` database. The actual setup command created exactly
  `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs` and
  `checkpoint_writes` there, with no business tables mixed in.
- Two independent Python processes completed the live pause/resume proof:
  process 12300 persisted the interrupted snapshot and closed; process 7788
  loaded that snapshot using the same opaque thread ID and reached END through
  `Command(resume=True)`. Five checkpoints remained in PostgreSQL afterward.
- The business database retained its tables, document/chunk counts and stored
  data fingerprints; no checkpoint tables appeared there. Both databases and
  the existing Docker container were preserved. `.env` was not edited; the
  checkpoint URL was supplied only to validation processes.
- An initial live connection attempt without a bounded timeout did not complete
  and was not counted as success. Validation succeeded with explicit libpq
  `connect_timeout=10`; the lifecycle also now bounds opening to 15 seconds.
  Failed setup attempts remain sanitized. No Groq/BGE/business workflow ran.

## Planned

JD approval/revision checkpoint integration, live co-pilot and
post-interview evaluation persistence integration remain separate feature tasks.
Docker Compose provisioning, production access/retention policies and application
lifecycle/pooling integration remain planned. A persisted interrupt does not
provide exactly-once external side effects; resumed nodes can restart, so future
business integrations must handle replay/idempotency explicitly.

## Implemented — Candidate Screening integration (#647498)

The actual Screening graph now supports supplied-saver compilation and trusted
internal PostgreSQL start/resume functions. It reuses this lifecycle, thread
validation and strict serializer; no new checkpoint tables, migrations or setup
behavior are introduced. Registered state is converted to JSON primitives and
reconstructed as strict domain models at graph boundaries. Default non-persistent
`prepare()`, `match()` and `screen()` behavior is unchanged.

Actual-graph unit tests verify pause after matching, saver-context closure and
resume without repeating completed matching. **Live PostgreSQL cross-process
Screening recovery is unverified on 08 Oct 2026:** local checkpoint configuration
is missing and Docker is unavailable. The 07 Oct foundation proof above uses a
different test graph and does not establish Screening recovery. An opt-in
two-process Screening proof is provided with mocked semantic calls; see
[Candidate Screening](candidate_screening.md) for the command and security limits.

Checkpointed qualifications require privacy protection. Thread snapshot equality
is an accidental-reuse guard, not ownership enforcement or concurrency locking;
one trusted writer per thread is required. Authorization, retention/deletion and
production application integration remain planned.
