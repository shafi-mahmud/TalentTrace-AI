# Project Structure

## Implemented — current foundation

- `frontend/` is a minimal React, Vite, and TypeScript application. It currently displays a simple project-skeleton page.
- `backend/` is a modular FastAPI application. It currently provides centralized settings, CORS configuration, automatic OpenAPI documentation, and `GET /api/v1/health`.
- `backend/app/db/` provides one shared SQLAlchemy `DeclarativeBase` and lazy factories for an async PostgreSQL engine and sessions. `DATABASE_URL` is optional during application import, is stored as a secret value when configured, and must use the `postgresql+asyncpg` scheme. This foundation does not connect to PostgreSQL or persist data by itself.
- `backend/app/services/`, `repositories/`, and the integration packages other than `integrations/llm/` remain boundaries for future code.
- `backend/app/rag/` contains validated internal company-policy source and chunk contracts, deterministic heading-aware text chunking, and an explicitly synthetic deterministic lexical retrieval adapter for the trainer demo. This adapter is not semantic or vector retrieval.
- `backend/app/agents/jd/` contains a bounded three-node LangGraph workflow that retrieves synthetic demo policy context, invokes the Groq integration, validates model citations, and returns an unapproved job-description draft. It does not persist or approve the draft.
- `backend/app/integrations/llm/` contains the Groq structured-output adapter used by the Job Description workflow. The API key remains optional during application startup and is required only when generation is invoked.

## Planned — future functionality

- `backend/app/agents/` contains four bounded workflow packages: `jd`, `screening`, `copilot`, and `evaluation`. The `jd` package has the limited trainer-demo workflow described above; the other three remain planned. They are Python modules inside the FastAPI modular monolith, not separate microservices.
- ORM business models, `KnowledgeDocument` and `KnowledgeChunk`, an Alembic migration environment and revisions, pgvector, a PostgreSQL Docker service, repositories, persistence behavior, and a LangGraph PostgreSQL checkpointer remain planned.
- Production Company Policy RAG embeddings, PostgreSQL/pgvector vector storage, similarity retrieval, and private policy ingestion remain planned. The deterministic lexical demo adapter is not a substitute for this architecture.
- Background processing and concrete external integration implementations remain planned; their current packages are architectural boundaries only.
- `job-publishing-mcp/` marks the boundary for a future lightweight, TalentTrace-owned MCP server for approved job publishing. It is not implemented.

Authentication, persistence, human approval/revision, the remaining hiring workflows, and other external integrations remain planned work.
