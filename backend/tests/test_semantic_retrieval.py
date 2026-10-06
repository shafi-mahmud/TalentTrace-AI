import asyncio
import hashlib
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from app.rag.contracts import CompanyPolicySource, PolicyChunk, PolicyChunkMetadata, chunk_sha256
from app.rag.embeddings import BGEEmbeddingService, BGE_QUERY_INSTRUCTION, EmbeddingError
from app.rag.retrieval import PolicyRetrievalError, RetrievedPolicyChunk
from app.rag.semantic_retrieval import SemanticCompanyPolicyRetriever, build_policy_search_query
from app.schemas.job_description import JobDescriptionGenerationRequest


VECTOR = (1.0,) + (0.0,) * 383
DOCUMENT_ID = uuid4()


def request(complete=False):
    fields = dict(
        job_title="Privacy Engineer",
        role_summary="Protect confidential hiring information and design secure data handling.",
        responsibilities=["Protect personal information", "Review secure data handling"],
        required_skills=["Python", "Data protection"],
    )
    if complete:
        fields.update(
            preferred_skills=["PostgreSQL"], department="Engineering",
            employment_type="full_time", work_arrangement="hybrid", location="Dhaka",
            seniority_level="Senior", minimum_experience_years=0,
            education_requirements=["Computer science degree"],
        )
    return JobDescriptionGenerationRequest(**fields)


def retrieved_result():
    source = CompanyPolicySource(
        source_id=uuid4(), source_version="test-v1", title="Synthetic Privacy Policy",
        text="# Privacy\nProtect confidential information.",
    )
    fingerprint = hashlib.sha256(source.source_version.encode()).hexdigest()[:16]
    chunk = PolicyChunk(text=source.text, metadata=PolicyChunkMetadata(
        source_id=source.source_id, source_version=source.source_version,
        source_content_sha256=source.content_sha256,
        citation_id=f"policy:{source.source_id.hex}:{fingerprint}:{source.content_sha256[:16]}:0000",
        chunk_index=0, chunk_sha256=chunk_sha256(source.text), token_count=6,
        heading_paths=(("Privacy",),),
    ))
    return (RetrievedPolicyChunk(source=source.source_metadata(), chunk=chunk),)


class FakeEmbedding:
    def __init__(self, failure=None):
        self.failure = failure
        self.queries = []
        self.thread_id = None

    def embed_query(self, text):
        self.thread_id = threading.get_ident()
        self.queries.append(text)
        if self.failure:
            raise self.failure
        return VECTOR

    def embed_documents(self, texts):
        raise AssertionError("Semantic retrieval must use embed_query")


class FakeRepository:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []
        self.result = retrieved_result()

    async def find_nearest_chunks(self, document_id, vector, *, top_k):
        self.calls.append((document_id, vector, top_k))
        if self.failure:
            raise self.failure
        return self.result


def adapter(repository, embedding, **kwargs):
    return SemanticCompanyPolicyRetriever(
        repository=repository, embedding_service=embedding,
        document_id=kwargs.pop("document_id", DOCUMENT_ID), **kwargs,
    )


def test_deterministic_labeled_query_represents_all_relevant_fields():
    expected = "\n".join([
        "Job title: Privacy Engineer",
        "Role summary: Protect confidential hiring information and design secure data handling.",
        "Responsibilities: Protect personal information; Review secure data handling",
        "Required skills: Python; Data protection", "Preferred skills: PostgreSQL",
        "Department: Engineering", "Employment type: full time", "Work arrangement: hybrid",
        "Location: Dhaka", "Seniority: Senior", "Minimum experience years: 0",
        "Education: Computer science degree",
    ])
    assert build_policy_search_query(request(True)) == expected
    assert build_policy_search_query(request(True)) == expected
    assert "EmploymentType" not in expected
    assert "{" not in expected


def test_minimal_query_omits_missing_optional_fields():
    query = build_policy_search_query(request())
    assert len(query.splitlines()) == 4
    assert "None" not in query
    assert "Preferred skills:" not in query
    assert BGE_QUERY_INSTRUCTION not in query


@pytest.mark.parametrize("top_k", [1, 4, 5])
def test_embed_query_document_scope_limit_and_results_pass_through(top_k):
    repository, embedding = FakeRepository(), FakeEmbedding()
    retriever = adapter(repository, embedding, top_k=top_k)
    result = asyncio.run(retriever.retrieve(request()))
    assert result is repository.result
    assert result[0] is repository.result[0]
    assert embedding.queries == [build_policy_search_query(request())]
    assert repository.calls == [(DOCUMENT_ID, VECTOR, top_k)]
    assert embedding.thread_id != threading.get_ident()
    assert BGE_QUERY_INSTRUCTION not in embedding.queries[0]


def test_constructor_is_lazy_and_default_limit_is_four():
    repository, embedding = FakeRepository(), FakeEmbedding()
    retriever = adapter(repository, embedding)
    assert not repository.calls and not embedding.queries
    asyncio.run(retriever.retrieve(request()))
    assert repository.calls[0][2] == 4


@pytest.mark.parametrize("top_k", [0, 6, -1, True, False, 1.5, None, "private-marker"])
def test_invalid_constructor_limit_is_controlled(top_k):
    with pytest.raises(PolicyRetrievalError) as error:
        adapter(FakeRepository(), FakeEmbedding(), top_k=top_k)
    assert "private-marker" not in str(error.value)


@pytest.mark.parametrize("document_id", [None, "private-marker", str(DOCUMENT_ID), 42])
def test_constructor_requires_explicit_document_uuid(document_id):
    with pytest.raises(PolicyRetrievalError) as error:
        adapter(FakeRepository(), FakeEmbedding(), document_id=document_id)
    assert "private-marker" not in str(error.value)


@pytest.mark.parametrize("failure", [EmbeddingError("private-marker query/vector/path"), RuntimeError("private-marker")])
def test_embedding_failure_is_sanitized_and_does_not_query_repository(failure):
    repository = FakeRepository()
    retriever = adapter(repository, FakeEmbedding(failure))
    with pytest.raises(PolicyRetrievalError) as error:
        asyncio.run(retriever.retrieve(request()))
    assert "private-marker" not in str(error.value)
    assert str(VECTOR) not in str(error.value)
    assert error.value.__suppress_context__
    assert not repository.calls


@pytest.mark.parametrize("message", [
    "Company-policy document was not found.",
    "No usable company-policy chunks are available for this document.",
    "Company-policy database retrieval failed.",
])
def test_controlled_repository_errors_pass_through(message):
    failure = PolicyRetrievalError(message)
    retriever = adapter(FakeRepository(failure), FakeEmbedding())
    with pytest.raises(PolicyRetrievalError) as error:
        asyncio.run(retriever.retrieve(request()))
    assert error.value is failure


def test_unexpected_repository_failure_is_sanitized():
    retriever = adapter(FakeRepository(RuntimeError("private-marker database/vector")), FakeEmbedding())
    with pytest.raises(PolicyRetrievalError) as error:
        asyncio.run(retriever.retrieve(request()))
    assert str(error.value) == "Semantic company-policy retrieval failed."
    assert error.value.__suppress_context__


def test_mutated_invalid_request_is_rejected_before_embedding():
    invalid = request().model_copy(update={"role_summary": "private-marker\x00"})
    repository, embedding = FakeRepository(), FakeEmbedding()
    with pytest.raises(PolicyRetrievalError) as error:
        asyncio.run(adapter(repository, embedding).retrieve(invalid))
    assert "private-marker" not in str(error.value)
    assert not embedding.queries and not repository.calls


def test_non_request_query_construction_failure_is_controlled():
    with pytest.raises(PolicyRetrievalError):
        build_policy_search_query({"prompt": "private-marker"})


def test_over_token_limit_is_rejected_without_encoding_or_silent_truncation():
    class LongTokenizer:
        def encode(self, text, *, add_special_tokens, truncation):
            assert text.startswith(BGE_QUERY_INSTRUCTION)
            assert text.count(BGE_QUERY_INSTRUCTION) == 1
            assert add_special_tokens is True and truncation is False
            return list(range(513))

    class Backend:
        tokenizer = LongTokenizer()

        def encode(self, *args, **kwargs):
            raise AssertionError("Over-limit query must not be encoded")

    long_request = request().model_copy(update={
        "role_summary": "Detailed privacy engineering requirements. " * 20,
    })
    assert len(build_policy_search_query(long_request)) > 800
    repository = FakeRepository()
    service = BGEEmbeddingService(backend_factory=Backend)
    with pytest.raises(PolicyRetrievalError) as error:
        asyncio.run(adapter(repository, service).retrieve(long_request))
    assert "BGE token limit" in str(error.value)
    assert long_request.role_summary not in str(error.value)
    assert not repository.calls


def test_fresh_import_does_not_load_model_create_engine_or_connect():
    code = """
import asyncpg
import sqlalchemy.ext.asyncio as db
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected database initialization')
asyncpg.connect = forbidden
db.create_async_engine = forbidden
from app.rag.semantic_retrieval import SemanticCompanyPolicyRetriever
import sys
assert 'sentence_transformers' not in sys.modules
assert 'torch' not in sys.modules
assert 'app.agents.jd.workflow' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
    assert result.returncode == 0, "Semantic adapter import isolation check failed."
