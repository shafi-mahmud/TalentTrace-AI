import asyncio
import hashlib
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from app.rag import ingestion, retrieval, seed_demo_policy
from app.rag.contracts import CompanyPolicySource, PolicyChunk, PolicyChunkMetadata, chunk_sha256
from app.rag.embeddings import EmbeddingError
from app.rag.ingestion import CompanyPolicyIngestionError, ingest_company_policy_source
from app.repositories.company_policy import PolicyPersistenceError


VECTOR = (1.0,) + (0.0,) * 383


def fixture_chunks(source):
    fingerprint = hashlib.sha256(source.source_version.encode()).hexdigest()[:16]
    return tuple(PolicyChunk(text=text, metadata=PolicyChunkMetadata(
        source_id=source.source_id, source_version=source.source_version,
        source_content_sha256=source.content_sha256,
        citation_id=f"policy:{source.source_id.hex}:{fingerprint}:{source.content_sha256[:16]}:{index:04d}",
        chunk_index=index, chunk_sha256=chunk_sha256(text), token_count=len(text.split()),
        heading_paths=(("Synthetic",),),
    )) for index, text in enumerate(("Synthetic policy section one.", "Synthetic policy section two.")))


class FakeEmbedding:
    def __init__(self, failure=None, wrong_count=False):
        self.failure = failure
        self.wrong_count = wrong_count
        self.texts = None
        self.thread_id = None

    def embed_documents(self, texts):
        self.texts = texts
        self.thread_id = threading.get_ident()
        if self.failure:
            raise self.failure
        return (VECTOR,) * (len(texts) - int(self.wrong_count))

    def embed_query(self, text):
        raise AssertionError("Ingestion must not embed a query")


class FakeRepository:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []
        self.document_id = uuid4()

    async def save_source_version(self, source, chunks, vectors):
        self.calls.append((source, chunks, vectors))
        if self.failure:
            raise self.failure
        return self.document_id


def patch_chunker(monkeypatch, source, failure=None):
    chunks = fixture_chunks(source)
    calls = []

    def semantic_chunker(input_source, *, embedding_service):
        calls.append((input_source, embedding_service, threading.get_ident()))
        if failure:
            raise failure
        return chunks

    monkeypatch.setattr(ingestion, "chunk_company_policy_for_semantic_retrieval", semantic_chunker)
    return chunks, calls


def test_demo_source_identity_and_normalized_contents_shared_with_lexical_retriever():
    source = retrieval.load_demo_company_policy_source()
    assert source.source_id == retrieval.DEMO_POLICY_SOURCE_ID
    assert source.source_version == "synthetic-demo-v1"
    assert source.title == retrieval.DEMO_POLICY_TITLE
    assert source.collection == "company_policy"
    lexical = retrieval.create_demo_company_policy_retriever()
    assert all(item.source == source.source_metadata() for item in lexical._chunks)
    assert source == retrieval.load_demo_company_policy_source()


def test_ingestion_uses_semantic_chunker_ordered_document_vectors_and_atomic_repository(monkeypatch):
    source = retrieval.load_demo_company_policy_source()
    chunks, chunk_calls = patch_chunker(monkeypatch, source)
    embedding, repository = FakeEmbedding(), FakeRepository()
    result = asyncio.run(ingest_company_policy_source(source, embedding_service=embedding, repository=repository))
    assert result == repository.document_id
    assert chunk_calls[0][:2] == (source, embedding)
    assert chunk_calls[0][2] != threading.get_ident()
    assert embedding.thread_id != threading.get_ident()
    assert embedding.texts == [chunk.text for chunk in chunks]
    assert repository.calls == [(source.source_metadata(), chunks, (VECTOR, VECTOR))]


def test_chunking_failure_is_controlled_and_skips_embedding_and_persistence(monkeypatch):
    source = retrieval.load_demo_company_policy_source()
    patch_chunker(monkeypatch, source, ValueError("private-marker policy/path"))
    embedding, repository = FakeEmbedding(), FakeRepository()
    with pytest.raises(CompanyPolicyIngestionError) as error:
        asyncio.run(ingest_company_policy_source(source, embedding_service=embedding, repository=repository))
    assert str(error.value) == "Semantic policy chunking/tokenization failed."
    assert error.value.__suppress_context__
    assert embedding.texts is None and not repository.calls


@pytest.mark.parametrize("failure", [EmbeddingError("private-marker vector"), RuntimeError("private-marker")])
def test_embedding_failure_is_controlled_and_skips_repository(monkeypatch, failure):
    source = retrieval.load_demo_company_policy_source()
    patch_chunker(monkeypatch, source)
    repository = FakeRepository()
    with pytest.raises(CompanyPolicyIngestionError) as error:
        asyncio.run(ingest_company_policy_source(source, embedding_service=FakeEmbedding(failure), repository=repository))
    assert str(error.value) == "Policy document embedding failed."
    assert error.value.__suppress_context__
    assert not repository.calls


def test_embedding_count_mismatch_never_reaches_repository(monkeypatch):
    source = retrieval.load_demo_company_policy_source()
    patch_chunker(monkeypatch, source)
    repository = FakeRepository()
    with pytest.raises(CompanyPolicyIngestionError, match="one vector per chunk"):
        asyncio.run(ingest_company_policy_source(source, embedding_service=FakeEmbedding(wrong_count=True), repository=repository))
    assert not repository.calls


@pytest.mark.parametrize("failure", [PolicyPersistenceError("private-marker SQL"), RuntimeError("private-marker credentials")])
def test_persistence_failure_is_sanitized(monkeypatch, failure):
    source = retrieval.load_demo_company_policy_source()
    patch_chunker(monkeypatch, source)
    with pytest.raises(CompanyPolicyIngestionError) as error:
        asyncio.run(ingest_company_policy_source(source, embedding_service=FakeEmbedding(), repository=FakeRepository(failure)))
    assert str(error.value) == "Policy persistence failed."
    assert error.value.__suppress_context__


def test_duplicate_source_or_chunk_conflict_has_clear_controlled_message(monkeypatch):
    source = retrieval.load_demo_company_policy_source()
    patch_chunker(monkeypatch, source)
    failure = PolicyPersistenceError("Policy source version or chunk conflicts with stored data.")
    with pytest.raises(CompanyPolicyIngestionError, match="already exists or conflicts"):
        asyncio.run(ingest_company_policy_source(source, embedding_service=FakeEmbedding(), repository=FakeRepository(failure)))


def test_demo_loader_failure_never_exposes_path(monkeypatch):
    def failed_read(*args, **kwargs):
        raise OSError("private-marker filesystem path")

    monkeypatch.setattr(Path, "read_text", failed_read)
    with pytest.raises(retrieval.PolicyRetrievalError) as error:
        retrieval.load_demo_company_policy_source()
    assert str(error.value) == "Synthetic company-policy context is unavailable."
    assert error.value.__suppress_context__


def test_seed_command_success_prints_only_safe_status_and_uuid(monkeypatch, capsys):
    document_id = uuid4()

    async def fake_seed():
        print("private-marker model diagnostics")
        print("private-marker stderr diagnostics", file=sys.stderr)
        return document_id

    monkeypatch.setattr(seed_demo_policy, "seed_demo_policy", fake_seed)
    assert seed_demo_policy.main() == 0
    output = capsys.readouterr()
    assert output.out == f"Demo policy seed succeeded. document_id={document_id}\n"
    assert output.err == ""


def test_seed_command_unexpected_failure_never_prints_private_details(monkeypatch, capsys):
    async def failed_seed():
        raise RuntimeError("private-marker secret/vector/SQL/path")

    monkeypatch.setattr(seed_demo_policy, "seed_demo_policy", failed_seed)
    assert seed_demo_policy.main() == 1
    output = capsys.readouterr()
    assert output.out == "Demo policy seed failed during initialization or cleanup.\n"
    assert not output.err


def test_seed_command_controlled_failure_reports_only_the_stage(monkeypatch, capsys):
    async def failed_seed():
        raise CompanyPolicyIngestionError("Policy document embedding failed.")

    monkeypatch.setattr(seed_demo_policy, "seed_demo_policy", failed_seed)
    assert seed_demo_policy.main() == 1
    output = capsys.readouterr()
    assert output.out == "Demo policy seed failed. Policy document embedding failed.\n"
    assert not output.err


def test_seed_source_loading_stage_is_controlled(monkeypatch):
    def failed_load():
        raise OSError("private-marker path")

    monkeypatch.setattr(seed_demo_policy, "load_demo_company_policy_source", failed_load)
    with pytest.raises(CompanyPolicyIngestionError, match="Synthetic demo source loading failed"):
        asyncio.run(seed_demo_policy.seed_demo_policy())


def test_seed_wiring_uses_factories_fixed_source_and_disposes_engine(monkeypatch):
    import app.db.session as session_module

    source = retrieval.load_demo_company_policy_source()
    document_id = uuid4()
    calls = []

    class Engine:
        async def dispose(self):
            calls.append("disposed")

    engine = Engine()
    factory = object()
    monkeypatch.setattr(session_module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(session_module, "create_database_session_factory", lambda value: factory if value is engine else None)
    monkeypatch.setattr(seed_demo_policy, "CompanyPolicyRepository", lambda value: value)
    embedding = object()
    monkeypatch.setattr(seed_demo_policy, "BGEEmbeddingService", lambda: embedding)

    async def fake_ingest(input_source, *, embedding_service, repository):
        assert input_source == source
        assert embedding_service is embedding and repository is factory
        calls.append("ingested")
        return document_id

    monkeypatch.setattr(seed_demo_policy, "ingest_company_policy_source", fake_ingest)
    assert asyncio.run(seed_demo_policy.seed_demo_policy()) == document_id
    assert calls == ["ingested", "disposed"]


def test_importing_ingestion_seed_and_application_has_no_database_model_or_llm_calls():
    code = """
import asyncpg
import groq
import sqlalchemy.ext.asyncio as db
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected database initialization')
asyncpg.connect = forbidden
db.create_async_engine = forbidden
groq.Groq = forbidden
groq.AsyncGroq = forbidden
from app.rag.ingestion import ingest_company_policy_source
from app.rag.seed_demo_policy import seed_demo_policy
from app.rag.embeddings import BGEEmbeddingService
BGEEmbeddingService._get_backend = forbidden
from app.rag.ingestion import ingest_company_policy_source as ingest
import app.rag.seed_demo_policy as seed
seed.seed_demo_policy = forbidden
from app.main import app
import sys
assert 'sentence_transformers' not in sys.modules
assert 'torch' not in sys.modules
assert app is not None
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
    assert result.returncode == 0, "Ingestion/application import isolation check failed."
