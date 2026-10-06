# Project Structure

## Implemented — initial skeleton

- `frontend/` is a minimal React, Vite, and TypeScript application. It currently displays a simple project-skeleton page.
- `backend/` is a modular FastAPI application. It currently provides centralized settings, CORS configuration, automatic OpenAPI documentation, and `GET /api/v1/health`.
- `backend/app/db/` provides one shared SQLAlchemy `DeclarativeBase` and lazy factories for an async PostgreSQL engine and sessions. `DATABASE_URL` is optional during application import, is stored as a secret value when configured, and must use the `postgresql+asyncpg` scheme. This foundation does not connect to PostgreSQL or persist data by itself.
- `backend/app/services/`, `repositories/`, and `integrations/` are package boundaries for future code. They contain no feature implementation yet.

## Planned — future functionality

- `backend/app/agents/` contains exactly four planned LangGraph workflow packages: `jd`, `screening`, `copilot`, and `evaluation`. They are Python modules inside the FastAPI modular monolith, not separate microservices. LangGraph is not implemented yet.
- ORM business models, `KnowledgeDocument` and `KnowledgeChunk`, an Alembic migration environment and revisions, pgvector, a PostgreSQL Docker service, repositories, persistence and retrieval behavior, and a LangGraph PostgreSQL checkpointer remain planned.
- `backend/app/rag/`, background work, and integration packages are reserved for later incremental tasks.
- `job-publishing-mcp/` marks the boundary for a future lightweight, TalentTrace-owned MCP server for approved job publishing. It is not implemented.

The skeleton proves the basic application structure only. Hiring workflows, authentication, persistence, AI orchestration, and external integrations remain planned work.
