import asyncio
import hashlib
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.rag.contracts import CompanyPolicySource, PolicyChunk, PolicyChunkMetadata, chunk_sha256
from app.rag.embeddings import BGE_MODEL_NAME
from app.rag.retrieval import PolicyRetrievalError
from app.repositories.company_policy import CompanyPolicyRepository


VECTOR = (1.0,) + (0.0,) * 383
DOCUMENT_ID = uuid4()


def stored_rows():
    source = CompanyPolicySource(
        source_id=uuid4(), source_version="synthetic-v1", title="Synthetic Test Policy",
        text="# Engineering\nWrite automated tests.\n# Privacy\nProtect confidential information.",
    )
    fingerprint = hashlib.sha256(source.source_version.encode()).hexdigest()[:16]
    chunks = tuple(PolicyChunk(
        text=body,
        metadata=PolicyChunkMetadata(
            source_id=source.source_id, source_version=source.source_version,
            source_content_sha256=source.content_sha256,
            citation_id=f"policy:{source.source_id.hex}:{fingerprint}:{source.content_sha256[:16]}:{index:04d}",
            chunk_index=index, chunk_sha256=chunk_sha256(body), token_count=len(body.split()),
            heading_paths=((heading,),),
        ),
    ) for index, (heading, body) in enumerate((
        ("Engineering", "Write automated tests."),
        ("Privacy", "Protect confidential information."),
        ("Quality", "Review engineering changes."),
    )))
    source_row = {
        "source": source.source_id, "source_version": source.source_version,
        "title": source.title, "content_sha256": source.content_sha256,
    }
    rows = [{
        "citation_id": chunk.metadata.citation_id, "chunk_index": chunk.metadata.chunk_index,
        "chunk_sha256": chunk.metadata.chunk_sha256, "chunk_text": chunk.text,
        "token_count": chunk.metadata.token_count,
        "chunk_metadata": {"heading_paths": [list(path) for path in chunk.metadata.heading_paths]},
    } for chunk in chunks]
    return source, chunks, source_row, rows


class MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class QuerySession:
    def __init__(self, source, rows, failure):
        self.source = source
        self.rows = rows
        self.failure = failure
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, statement):
        self.statements.append(statement)
        if self.failure:
            raise self.failure
        return MappingResult(([self.source] if self.source else []) if len(self.statements) == 1 else self.rows)


class QueryFactory:
    def __init__(self, source=None, rows=(), failure=None):
        self.session = QuerySession(source, rows, failure)
        self.opened = False

    def __call__(self):
        self.opened = True
        return self.session


def search(factory, vector=VECTOR, top_k=4, document_id=DOCUMENT_ID):
    return asyncio.run(CompanyPolicyRepository(factory).find_nearest_chunks(
        document_id, vector, top_k=top_k,
    ))


def test_source_chunk_metadata_reconstructed_without_embeddings():
    source, chunks, source_row, rows = stored_rows()
    # Database ordering is retained, rather than resorted by Python/chunk index.
    factory = QueryFactory(source_row, [rows[2], rows[0]])
    results = search(factory, top_k=2)
    assert [result.chunk for result in results] == [chunks[2], chunks[0]]
    assert all(result.source == source.source_metadata() for result in results)
    for result in results:
        public = result.model_dump()
        assert set(public) == {"source", "chunk"}
        assert set(public["chunk"]) == {"text", "metadata"}
        assert "embedding" not in result.model_dump_json()
        assert "document_id" not in public
        assert result.model_config["frozen"]


@pytest.mark.parametrize("top_k", [1, 3, 5])
def test_sql_cosine_distance_scope_collection_model_order_and_limit(top_k):
    _, _, source_row, rows = stored_rows()
    factory = QueryFactory(source_row, rows[:1])
    search(factory, top_k=top_k)
    source_query, chunk_query = factory.session.statements
    source_sql = str(source_query.compile(dialect=postgresql.dialect()))
    compiled = chunk_query.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "knowledge_documents.id =" in source_sql
    assert "knowledge_documents.knowledge_type =" in source_sql
    assert "company_policy" in source_query.compile().params.values()
    assert DOCUMENT_ID in source_query.compile().params.values()
    assert "knowledge_chunks.document_id =" in sql
    assert "knowledge_chunks.knowledge_type =" in sql
    assert "knowledge_chunks.embedding_model =" in sql
    assert DOCUMENT_ID in compiled.params.values()
    assert "company_policy" in compiled.params.values()
    assert BGE_MODEL_NAME in compiled.params.values()
    # <=> is PostgreSQL pgvector cosine distance, not L2/inner product.
    assert " <=> " in sql
    assert " <-> " not in sql
    ordering = sql.split("ORDER BY ")[1].split("LIMIT")[0]
    assert ordering.index("<=>") < ordering.index("chunk_index ASC") < ordering.index("citation_id ASC")
    assert "ASC" in ordering.split(",")[0]
    assert chunk_query._limit_clause.value == top_k
    assert "embedding" not in chunk_query.selected_columns.keys()
    assert "hnsw" not in sql.lower() and "ivfflat" not in sql.lower()


@pytest.mark.parametrize("bad_vector", [
    (), (1.0,) * 383, (1.0,) * 385, (float("nan"),) + (0.0,) * 383,
    (float("inf"),) + (0.0,) * 383, (True,) + (0.0,) * 383,
    ("private-marker",) + (0.0,) * 383, (0.0,) * 384,
    (2.0,) + (0.0,) * 383, "private-marker", None,
])
def test_invalid_query_vectors_rejected_before_database_access(bad_vector):
    factory = QueryFactory()
    with pytest.raises(PolicyRetrievalError) as error:
        search(factory, vector=bad_vector)
    assert "private-marker" not in str(error.value)
    assert not factory.opened


@pytest.mark.parametrize("bad_top_k", [0, -1, 6, True, False, 1.5, "private-marker", None])
def test_invalid_top_k_rejected_before_database_access(bad_top_k):
    factory = QueryFactory()
    with pytest.raises(PolicyRetrievalError) as error:
        search(factory, top_k=bad_top_k)
    assert "private-marker" not in str(error.value)
    assert not factory.opened


def test_invalid_document_id_rejected_before_database_access():
    factory = QueryFactory()
    with pytest.raises(PolicyRetrievalError):
        search(factory, document_id="private-marker")
    assert not factory.opened


def test_missing_or_filtered_document_has_controlled_failure_without_chunk_query():
    factory = QueryFactory()
    with pytest.raises(PolicyRetrievalError, match="document was not found"):
        search(factory)
    assert len(factory.session.statements) == 1


def test_existing_document_without_usable_chunks_has_controlled_failure():
    _, _, source_row, _ = stored_rows()
    factory = QueryFactory(source_row)
    with pytest.raises(PolicyRetrievalError, match="No usable company-policy chunks"):
        search(factory)


@pytest.mark.parametrize("failure", [
    SQLAlchemyError("private-marker SQL/credentials/vector"),
    OSError("private-marker connection details"),
    RuntimeError("private-marker driver details"),
])
def test_database_failure_is_sanitized(failure):
    factory = QueryFactory(failure=failure)
    with pytest.raises(PolicyRetrievalError) as error:
        search(factory)
    assert str(error.value) == "Company-policy database retrieval failed."
    assert error.value.__suppress_context__


@pytest.mark.parametrize("change", [
    {"chunk_metadata": {"heading_paths": [], "api_key": "private-marker"}},
    {"chunk_sha256": "f" * 64},
    {"chunk_text": "private-marker\x00"},
    {"citation_id": "private-marker"},
])
def test_invalid_stored_context_is_rejected_without_echo(change):
    _, _, source_row, rows = stored_rows()
    factory = QueryFactory(source_row, [{**rows[0], **change}])
    with pytest.raises(PolicyRetrievalError) as error:
        search(factory)
    assert str(error.value) == "Stored company-policy context is invalid."
    assert error.value.__suppress_context__


def test_import_does_not_create_engine_connect_or_load_model():
    code = """
import asyncpg
import sqlalchemy.ext.asyncio as db
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected database initialization')
asyncpg.connect = forbidden
db.create_async_engine = forbidden
from app.repositories.company_policy import CompanyPolicyRepository
import sys
assert 'sentence_transformers' not in sys.modules
assert 'torch' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
    assert result.returncode == 0, "Repository import isolation check failed."
