"""Explicit local policy preload: python -m app.rag.ingest_policy_file."""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.rag.contracts import CompanyPolicySource
from app.rag.ingestion import CompanyPolicyIngestionError, ingest_company_policy_source
from app.rag.policy_files import PolicyFileError, extract_policy_text


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal errors can echo arbitrary supplied values.
        raise PolicyFileError("Invalid command options. Use --help for usage.")


def load_policy_source(*, file: str | Path, title: str, version: str,
                       source_id: UUID | str | None = None) -> CompanyPolicySource:
    try:
        # Validate metadata before reading a potentially confidential document.
        identity = CompanyPolicySource(
            source_id=source_id if source_id is not None else uuid4(),
            source_version=version, title=title, text="Metadata validation placeholder.",
        )
        return CompanyPolicySource(
            source_id=identity.source_id, source_version=identity.source_version,
            title=identity.title, text=extract_policy_text(file),
        )
    except ValidationError:
        raise PolicyFileError("Policy metadata or extracted text failed validation.") from None


async def ingest_policy_file(source: CompanyPolicySource) -> UUID:
    # No DB, model, or external file activity takes place at module import.
    engine = None
    try:
        from app.db.session import create_database_engine, create_database_session_factory
        from app.rag.embeddings import BGEEmbeddingService
        from app.repositories.company_policy import CompanyPolicyRepository

        engine = create_database_engine()
        factory = create_database_session_factory(engine)
        return await ingest_company_policy_source(
            source, embedding_service=BGEEmbeddingService(),
            repository=CompanyPolicyRepository(factory),
        )
    except CompanyPolicyIngestionError:
        raise
    except Exception:
        raise CompanyPolicyIngestionError("Policy database initialization or ingestion failed.") from None
    finally:
        if engine is not None:
            await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(description="Preload one local Company Policy source version.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-id")
    try:
        args = parser.parse_args(argv)
        # Discard parser/model diagnostics without buffering private text in
        # memory or a log file. Only our fixed operational output reaches stdout.
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with redirect_stdout(sink), redirect_stderr(sink):
                source = load_policy_source(
                    file=args.file, title=args.title, version=args.version,
                    source_id=args.source_id,
                )
                document_id = asyncio.run(ingest_policy_file(source))
    except PolicyFileError as error:
        print(f"Policy ingestion failed. {error}")
        return 1
    except CompanyPolicyIngestionError as error:
        # Existing ingestion errors are fixed stage messages, never raw SQL.
        print(f"Policy ingestion failed. {error}")
        return 1
    except Exception:
        print("Policy ingestion failed during initialization or cleanup.")
        return 1
    print("Policy ingestion succeeded.")
    print(f"source_id={source.source_id}")
    print(f"document_id={document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
