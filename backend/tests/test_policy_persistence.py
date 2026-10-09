import asyncio
import importlib.util
import io
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, MetaData, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.base import Base
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.rag.chunking import ChunkingConfig, chunk_company_policy
from app.rag.contracts import CompanyPolicySource
from app.rag.embeddings import BGE_MODEL_NAME
from app.repositories.company_policy import CompanyPolicyRepository, PolicyPersistenceError


BACKEND = Path(__file__).resolve().parents[1]
UNIT_VECTOR = (1.0,) + (0.0,) * 383


class WhitespaceTokenCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


def policy_batch():
    source = CompanyPolicySource(
        source_id=UUID("01234567-89ab-cdef-0123-456789abcdef"),
        source_version="v1", title="Synthetic Test Policy",
        text="# Engineering\n" + "Secure engineering practices and automated tests. " * 120,
    )
    chunks = chunk_company_policy(
        source, WhitespaceTokenCounter(),
        ChunkingConfig(chunk_size_tokens=400, overlap_tokens=50),
    )
    assert len(chunks) > 1
    return source.source_metadata(), chunks, [UNIT_VECTOR] * len(chunks)


class RecordingSession:
    """Transaction test double; never represents a live database integration test."""

    def __init__(self, committed, failure=None):
        self.committed = committed
        self.failure = failure
        self.document = None
        self.did_commit = False
        self.did_rollback = False
        self.did_flush = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        session = self

        class Transaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                if exc_type:
                    session.did_rollback = True
                else:
                    session.did_commit = True
                    session.committed.append(session.document)

        return Transaction()

    def add(self, document):
        self.document = document

    async def flush(self):
        self.did_flush = True
        if self.failure:
            raise self.failure
        key = (self.document.knowledge_type, self.document.source, self.document.source_version)
        if any((row.knowledge_type, row.source, row.source_version) == key for row in self.committed):
            raise IntegrityError("private SQL", {}, Exception("private database details"))


class RecordingFactory:
    def __init__(self, failure=None):
        self.committed = []
        self.sessions = []
        self.failure = failure

    def __call__(self):
        session = RecordingSession(self.committed, self.failure)
        self.sessions.append(session)
        return session


def save(factory, batch):
    return asyncio.run(CompanyPolicyRepository(factory).save_source_version(*batch))


def test_complete_source_and_chunks_are_mapped_and_committed_together():
    source, chunks, vectors = policy_batch()
    factory = RecordingFactory()
    document_id = save(factory, (source, chunks, vectors))
    assert len(factory.committed) == 1
    document = factory.committed[0]
    assert document.id == document_id
    assert document.source == source.source_id
    assert document.source_version == source.source_version
    assert document.title == source.title
    assert document.content_sha256 == source.content_sha256
    assert document.knowledge_type == "company_policy"
    assert len(document.chunks) == len(chunks)
    for row, chunk in zip(document.chunks, chunks, strict=True):
        assert row.document_id == document_id
        assert row.document is document
        assert row.knowledge_type == "company_policy"
        assert row.citation_id == chunk.metadata.citation_id
        assert row.chunk_index == chunk.metadata.chunk_index
        assert row.chunk_sha256 == chunk.metadata.chunk_sha256
        assert row.chunk_text == chunk.text
        assert row.token_count == chunk.metadata.token_count
        assert row.chunk_metadata == {"heading_paths": [list(path) for path in chunk.metadata.heading_paths]}
        assert row.embedding_model == BGE_MODEL_NAME
        assert row.embedding == list(UNIT_VECTOR)
    assert factory.sessions[0].did_flush
    assert factory.sessions[0].did_commit
    assert not factory.sessions[0].did_rollback


@pytest.mark.parametrize("bad_vector", [
    (), (1.0,) * 383, (1.0,) * 385,
    (float("nan"),) + (0.0,) * 383,
    (float("inf"),) + (0.0,) * 383,
    (True,) + (0.0,) * 383,
    ("private-marker",) + (0.0,) * 383,
    (0.0,) * 384, (2.0,) + (0.0,) * 383,
    "private-marker", None,
])
def test_invalid_vectors_are_rejected_before_opening_session(bad_vector):
    source, chunks, vectors = policy_batch()
    vectors[-1] = bad_vector
    factory = RecordingFactory()
    with pytest.raises(PolicyPersistenceError) as error:
        save(factory, (source, chunks, vectors))
    assert "private-marker" not in str(error.value)
    assert not factory.sessions


@pytest.mark.parametrize("mutation", [
    {"source_id": UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")},
    {"source_version": "v2"},
    {"source_content_sha256": "f" * 64},
    {"chunk_sha256": "f" * 64},
    {"chunk_index": 10},
    {"citation_id": "policy:" + "f" * 32 + ":" + "f" * 16 + ":" + "f" * 16 + ":0000"},
    {"collection": "technical_reference"},
])
def test_foreign_or_invalid_chunk_metadata_is_rejected(mutation):
    source, chunks, vectors = policy_batch()
    changed = chunks[0].model_copy(update={
        "metadata": chunks[0].metadata.model_copy(update=mutation)
    })
    factory = RecordingFactory()
    with pytest.raises(PolicyPersistenceError):
        save(factory, (source, (changed, *chunks[1:]), vectors))
    assert not factory.sessions


def test_non_policy_source_and_arbitrary_metadata_cannot_cross_boundary():
    source, chunks, vectors = policy_batch()
    factory = RecordingFactory()
    for update in ({"collection": "technical_reference"}, {"api_key": "private-marker"}):
        with pytest.raises(PolicyPersistenceError) as error:
            save(factory, (source.model_copy(update=update), chunks, vectors))
        assert "private-marker" not in str(error.value)
    assert not factory.sessions


def test_empty_or_mismatched_batch_is_rejected():
    source, chunks, vectors = policy_batch()
    factory = RecordingFactory()
    for batch in ((source, (), ()), (source, chunks, vectors[:-1])):
        with pytest.raises(PolicyPersistenceError):
            save(factory, batch)
    assert not factory.sessions


def test_duplicate_chunk_identity_in_batch_is_rejected():
    source, chunks, vectors = policy_batch()
    factory = RecordingFactory()
    with pytest.raises(PolicyPersistenceError):
        save(factory, (source, (chunks[0], chunks[0]), vectors[:2]))
    assert not factory.sessions


def test_duplicate_source_version_rolls_back_without_overwrite():
    batch = policy_batch()
    factory = RecordingFactory()
    first_id = save(factory, batch)
    with pytest.raises(PolicyPersistenceError, match="conflicts with stored data") as error:
        save(factory, batch)
    assert "private" not in str(error.value)
    assert len(factory.committed) == 1
    assert factory.committed[0].id == first_id
    assert factory.sessions[-1].did_rollback
    assert not factory.sessions[-1].did_commit


@pytest.mark.parametrize("failure", [
    IntegrityError("private SQL", {"text": "private-marker"}, Exception("private-marker")),
    SQLAlchemyError("private-marker"),
])
def test_database_failure_rolls_back_entire_version_and_is_sanitized(failure):
    factory = RecordingFactory(failure)
    with pytest.raises(PolicyPersistenceError) as error:
        save(factory, policy_batch())
    assert "private-marker" not in str(error.value)
    assert error.value.__suppress_context__
    assert not factory.committed
    assert factory.sessions[0].did_rollback
    assert not factory.sessions[0].did_commit


def test_vector_dimension_and_required_columns():
    table = KnowledgeChunk.__table__
    assert table.c.embedding.type.dim == 384
    assert str(table.c.embedding.type.compile(dialect=postgresql.dialect())) == "VECTOR(384)"
    assert all(not column.nullable for column in table.columns)
    assert set(KnowledgeDocument.__table__.c.keys()) == {
        "id", "knowledge_type", "source", "source_version", "title", "content_sha256",
    }
    assert set(table.c.keys()) == {
        "id", "document_id", "knowledge_type", "citation_id", "chunk_index",
        "chunk_sha256", "chunk_text", "token_count", "metadata", "embedding_model", "embedding",
    }
    metadata_check = next(c for c in table.constraints if c.name == "ck_chunk_metadata")
    assert "metadata - 'heading_paths'" in str(metadata_check.sqltext)
    assert "'{}'::jsonb" in str(metadata_check.sqltext)


def test_foreign_key_enforces_same_document_and_collection():
    foreign_key = next(c for c in KnowledgeChunk.__table__.constraints if isinstance(c, ForeignKeyConstraint))
    assert list(foreign_key.column_keys) == ["document_id", "knowledge_type"]
    assert [element.target_fullname for element in foreign_key.elements] == [
        "knowledge_documents.id", "knowledge_documents.knowledge_type",
    ]
    assert foreign_key.ondelete == "CASCADE"
    for table in (KnowledgeDocument.__table__, KnowledgeChunk.__table__):
        collection_check = next(c for c in table.constraints if isinstance(c, CheckConstraint) and "collection" in c.name)
        assert "'company_policy', 'technical_reference'" in str(collection_check.sqltext)
    uniques = {tuple(c.columns.keys()) for c in KnowledgeChunk.__table__.constraints if isinstance(c, UniqueConstraint)}
    assert ("citation_id",) in uniques
    assert ("document_id", "chunk_index") in uniques


def test_fresh_model_import_cannot_create_engine_or_connect():
    code = """
import asyncpg
import sqlalchemy.ext.asyncio as db
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected database initialization')
asyncpg.connect = forbidden
db.create_async_engine = forbidden
from app.db.models import KnowledgeDocument, KnowledgeChunk
assert KnowledgeChunk.__table__.c.embedding.type.dim == 384
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, timeout=30)
    # Never include child output/environment in assertion messages.
    assert result.returncode == 0, "Model import isolation check failed."


def alembic_config():
    output = io.StringIO()
    config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    return config, output


def test_offline_migration_creates_extension_before_vector_tables(monkeypatch):
    import app.db.session as session_module

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline migrations must not create an engine")

    monkeypatch.setattr(session_module, "create_database_engine", forbidden)
    config, output = alembic_config()
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert sql.index("CREATE EXTENSION IF NOT EXISTS vector") < sql.index("CREATE TABLE knowledge_documents")
    assert "CREATE TABLE knowledge_chunks" in sql
    assert "embedding VECTOR(384) NOT NULL" in sql
    assert "FOREIGN KEY(document_id, knowledge_type)" in sql
    assert "ON DELETE CASCADE" in sql
    assert "UNIQUE (citation_id)" in sql
    assert "UNIQUE (document_id, chunk_index)" in sql
    assert "UNIQUE (knowledge_type, source, source_version)" in sql
    assert "hnsw" not in sql.lower()
    assert "ivfflat" not in sql.lower()


def test_migration_snapshot_matches_orm_schema(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "knowledge_revision", BACKEND / "alembic/versions/0001_company_policy_knowledge.py"
    )
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    metadata = MetaData()
    monkeypatch.setattr(revision.op, "execute", lambda sql: None)
    monkeypatch.setattr(revision.op, "create_table", lambda name, *items: Table(name, metadata, *items))
    revision.upgrade()
    # Later business revisions register additional tables in shared metadata.
    assert set(metadata.tables) == {"knowledge_documents", "knowledge_chunks"}
    assert set(metadata.tables).issubset(Base.metadata.tables)
    for name, migrated in metadata.tables.items():
        model = Base.metadata.tables[name]
        assert list(migrated.c.keys()) == list(model.c.keys())
        for column in migrated.columns:
            expected = model.c[column.name]
            assert column.nullable == expected.nullable
            assert column.primary_key == expected.primary_key
            assert str(column.type.compile(dialect=postgresql.dialect())) == str(expected.type.compile(dialect=postgresql.dialect()))
        migrated_constraints = {c.name: c for c in migrated.constraints if c.name}
        model_constraints = {c.name: c for c in model.constraints if c.name}
        assert set(migrated_constraints) == set(model_constraints)
        for constraint_name, constraint in migrated_constraints.items():
            expected = model_constraints[constraint_name]
            if isinstance(constraint, CheckConstraint):
                assert str(constraint.sqltext) == str(expected.sqltext)
            elif isinstance(constraint, UniqueConstraint):
                assert list(constraint.columns.keys()) == list(expected.columns.keys())
            elif isinstance(constraint, ForeignKeyConstraint):
                assert constraint.column_keys == expected.column_keys
                assert [e.target_fullname for e in constraint.elements] == [e.target_fullname for e in expected.elements]
                assert constraint.ondelete == expected.ondelete


def test_offline_downgrade_drops_child_first_and_preserves_shared_extension():
    config, output = alembic_config()
    command.downgrade(config, "head:base", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP TABLE knowledge_chunks") < sql.index("DROP TABLE knowledge_documents")
    assert "DROP EXTENSION" not in sql
