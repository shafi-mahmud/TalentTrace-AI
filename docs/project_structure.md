# Project Structure

## Implemented — initial skeleton

- `frontend/` is a minimal React, Vite, and TypeScript application. It currently displays a simple project-skeleton page.
- `backend/` is a modular FastAPI application. It currently provides centralized settings, CORS configuration, automatic OpenAPI documentation, and `GET /api/v1/health`.
- `backend/app/db/` provides one shared SQLAlchemy `DeclarativeBase` and lazy factories for an async PostgreSQL engine and sessions. `DATABASE_URL` is optional during application import, is stored as a secret value when configured, and must use the `postgresql+asyncpg` scheme. This foundation does not connect to PostgreSQL or persist data by itself.
- `backend/app/services/`, `repositories/`, and `integrations/` are package boundaries for future code. They contain no feature implementation yet.

## Implemented — PostgreSQL checkpoint foundation

- `backend/app/db/checkpointer.py` provides the official async LangGraph
  PostgreSQL saver lifecycle with strict serialization. A separate checkpoint
  database on the same PostgreSQL instance keeps LangGraph-owned tables apart
  from application tables and Alembic. Setup is explicit through
  `python -m app.db.setup_checkpointer`; import/startup remains lazy.
- `backend/app/db/workflow_threads.py` validates opaque UUID-based identifiers
  in the four workflow namespaces, without implementing those workflows.
- See [checkpoint storage](checkpoint_storage.md) for configuration, setup,
  ownership, Windows async compatibility and the two-process validation helper.
  This establishes infrastructure only; it does not checkpoint the JD workflow.
- **Implemented and verified — 07 Oct 2026:** live setup in a separate database
  on the preserved PostgreSQL instance and a genuine two-process interrupt/resume
  proof passed. Business/RAG tables and data fingerprints remained unchanged.
  All 35 focused tests and 50 backend tests on this branch passed.

## Implemented — standalone MCP job-publishing foundation

- `job-publishing-mcp/` contains a TalentTrace-owned official Python MCP SDK v2
  stdio server with one `publish_job` tool, a strict `JobCircular` contract and
  an async Discord webhook adapter. Credentials stay server-side; mentions are
  disabled, oversized payloads are rejected and provider failures are sanitized.
- Mocked tests verify the adapter and MCP protocol. Real Discord smoke
  verification is pending. Backend MCP client/chatbot integration, JD approval
  enforcement and other destinations remain planned. No JD workflow or frontend
  integration is included. See [job-publishing MCP](../job-publishing-mcp/README.md).

## Planned — future functionality

- `backend/app/agents/` contains exactly four planned LangGraph workflow packages: `jd`, `screening`, `copilot`, and `evaluation`. They are Python modules inside the FastAPI modular monolith, not separate microservices. Checkpoint infrastructure is implemented; business workflow integration remains planned on this infrastructure branch.
- ORM business models, `KnowledgeDocument` and `KnowledgeChunk`, an Alembic migration environment and revisions, pgvector, a PostgreSQL Docker service, repositories, persistence and retrieval behavior remain planned on this infrastructure branch. The checkpoint database is provisioned separately; Docker Compose automation and business workflow persistence integration remain planned.
- `backend/app/rag/`, background work, and integration packages are reserved for later incremental tasks.
- Integration of the standalone job-publishing MCP server into approved JD publishing remains planned; its current implementation is described above.

The skeleton and checkpoint foundation establish application structure and reusable state persistence. Hiring workflows, authentication, business persistence, workflow-specific AI orchestration, and external integrations remain planned on this branch.
