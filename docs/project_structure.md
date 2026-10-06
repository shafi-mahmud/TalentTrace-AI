# Project Structure

## Implemented — current foundation

- `frontend/` is a React, Vite, and TypeScript application with a recruiter-facing Job Description form, a synthetic company-policy knowledge-source panel, and a generated draft view with policy citations and a human-review notice.
- `backend/` is a modular FastAPI application. It currently provides centralized settings, CORS configuration, automatic OpenAPI documentation, and `GET /api/v1/health`.
- `backend/app/db/` provides one shared SQLAlchemy `DeclarativeBase` and lazy factories for an async PostgreSQL engine and sessions. `DATABASE_URL` is optional during application import, is stored as a secret value when configured, and must use the `postgresql+asyncpg` scheme. This foundation does not connect to PostgreSQL or persist data by itself.
- `backend/app/services/`, `repositories/`, and the integration packages other than `integrations/llm/` remain boundaries for future code.
- `backend/app/rag/` contains validated internal company-policy source and chunk contracts, deterministic heading-aware text chunking, and an explicitly synthetic deterministic lexical retrieval adapter for the trainer demo. This adapter is not semantic or vector retrieval.
- `backend/app/rag/embeddings.py` provides a replaceable embedding protocol, a lazy local `BAAI/bge-small-en-v1.5` adapter, and a BGE tokenizer counter. It returns validated, normalized 384-dimensional vectors, prefixes retrieval queries only, and rejects text exceeding the model's 512-token limit instead of truncating it. Model loading happens only on explicit embedding or token-counting calls; importing the application does not load or download the model. The counter can share the encoder's model/tokenizer and excludes special tokens from chunk counts. This layer is not connected to the JD workflow or lexical demo retriever.
- `chunk_company_policy_for_semantic_retrieval()` in `backend/app/rag/chunking.py` prepares deterministic, citation-bearing company-policy chunks using BGE tokenizer counts: at most 400 tokens including headings, with up to 50 tokens of overlap at word boundaries and no tokenizer truncation. It reuses the existing chunking algorithm and uses only the embedding service's tokenizer, without generating vectors. The generic default remains 700/75; the lexical demo continues to explicitly use 500/50 with whitespace counting. This preparation helper is not semantic retrieval and is not wired into the JD workflow.
- `backend/app/agents/jd/` contains a bounded three-node LangGraph workflow that retrieves synthetic demo policy context, invokes the Groq integration, validates model citations, and returns an unapproved job-description draft. It does not persist or approve the draft.
- `backend/app/integrations/llm/` contains the Groq structured-output adapter used by the Job Description workflow. The API key remains optional during application startup and is required only when generation is invoked.

## Planned — future functionality

- `backend/app/agents/` contains four bounded workflow packages: `jd`, `screening`, `copilot`, and `evaluation`. The `jd` package has the limited trainer-demo workflow described above; the other three remain planned. They are Python modules inside the FastAPI modular monolith, not separate microservices.
- ORM business models, `KnowledgeDocument` and `KnowledgeChunk`, an Alembic migration environment and revisions, pgvector, a PostgreSQL Docker service, repositories, persistence behavior, and a LangGraph PostgreSQL checkpointer remain planned.
- Embedding persistence, PostgreSQL/pgvector vector storage, cosine similarity retrieval, a semantic `CompanyPolicyRetriever`, private policy ingestion, and replacement of the lexical demo in the JD workflow remain planned. Local embeddings and BGE tokenizer-backed chunk preparation are implemented foundations; they do not provide semantic retrieval yet.
- Background processing and concrete external integration implementations remain planned; their current packages are architectural boundaries only.
- `job-publishing-mcp/` marks the boundary for a future lightweight, TalentTrace-owned MCP server for approved job publishing. It is not implemented.

Authentication, persistence, human approval/revision, the remaining hiring workflows, and other external integrations remain planned work.
