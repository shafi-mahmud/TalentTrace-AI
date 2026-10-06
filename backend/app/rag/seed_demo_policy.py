"""Explicit synthetic demo seeding: python -m app.rag.seed_demo_policy."""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
from uuid import UUID

from app.rag.embeddings import BGEEmbeddingService
from app.rag.ingestion import CompanyPolicyIngestionError, ingest_company_policy_source
from app.rag.retrieval import load_demo_company_policy_source
from app.repositories.company_policy import CompanyPolicyRepository


async def seed_demo_policy() -> UUID:
    """Use local settings and the fixed demo file only; caller explicitly invokes it."""
    try:
        source = load_demo_company_policy_source()
    except Exception:
        raise CompanyPolicyIngestionError("Synthetic demo source loading failed.") from None
    try:
        # Configuration/database imports are deferred until the command is run.
        from app.db.session import create_database_engine, create_database_session_factory

        engine = create_database_engine()
        factory = create_database_session_factory(engine)
    except Exception:
        raise CompanyPolicyIngestionError("Demo database configuration/initialization failed.") from None
    try:
        return await ingest_company_policy_source(
            source, embedding_service=BGEEmbeddingService(),
            repository=CompanyPolicyRepository(factory),
        )
    finally:
        await engine.dispose()


def main() -> int:
    try:
        # This dedicated CLI reports only operational status; discard model-library
        # diagnostics/progress rather than emitting paths or incidental details.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            document_id = asyncio.run(seed_demo_policy())
    except CompanyPolicyIngestionError as error:
        print(f"Demo policy seed failed. {error}")
        return 1
    except Exception:
        print("Demo policy seed failed during initialization or cleanup.")
        return 1
    print(f"Demo policy seed succeeded. document_id={document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
