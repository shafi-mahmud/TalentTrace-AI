import asyncio
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.agents.jd import workflow as workflow_module
from app.api.routers import job_descriptions
from app.core.config import Settings
from app.main import app
from app.rag.retrieval import PolicyRetrievalError
from app.rag.semantic_retrieval import SemanticCompanyPolicyRetriever
from test_jd_workflow import request_contract


DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
DATABASE_URL = "postgresql+asyncpg://synthetic:synthetic@localhost/demo"


@pytest.fixture(autouse=True)
def clear_workflow_cache():
    workflow_module.get_job_description_workflow.cache_clear()
    yield
    workflow_module.get_job_description_workflow.cache_clear()


def configure(monkeypatch, *, database_url=DATABASE_URL, document_id=DOCUMENT_ID):
    configuration = Settings(
        _env_file=None, database_url=database_url,
        company_policy_document_id=document_id, groq_api_key=None,
    )
    monkeypatch.setattr(workflow_module, "settings", configuration)
    return configuration


async def post_request():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver",
    ) as client:
        return await client.post(
            "/api/v1/job-descriptions/generate",
            json=request_contract().model_dump(mode="json"),
        )


@pytest.mark.parametrize("missing", ["database", "document", "both"])
def test_missing_semantic_configuration_returns_safe_503(monkeypatch, missing):
    configure(
        monkeypatch,
        database_url=None if missing in {"database", "both"} else DATABASE_URL,
        document_id=None if missing in {"document", "both"} else DOCUMENT_ID,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Missing configuration must fail before resource construction")

    monkeypatch.setattr(workflow_module, "create_database_engine", forbidden)
    monkeypatch.setattr(workflow_module, "BGEEmbeddingService", forbidden)
    response = asyncio.run(post_request())
    assert response.status_code == 503
    assert response.json() == job_descriptions.MISSING_CONFIGURATION_RESPONSE


def test_factory_builds_semantic_retriever_with_explicit_uuid_lazily(monkeypatch):
    configuration = configure(monkeypatch)
    engine, factory, embedding, generator = object(), object(), object(), object()

    def create_engine(value):
        assert value is configuration
        return engine

    def create_sessions(value):
        assert value is engine
        return factory

    def create_generator(*, configuration):
        assert configuration is workflow_module.settings
        return generator

    monkeypatch.setattr(workflow_module, "create_database_engine", create_engine)
    monkeypatch.setattr(workflow_module, "create_database_session_factory", create_sessions)
    monkeypatch.setattr(workflow_module, "BGEEmbeddingService", lambda: embedding)
    monkeypatch.setattr(workflow_module, "GroqJobDescriptionGenerator", create_generator)
    import app.rag.retrieval as lexical_module

    def forbidden_lexical():
        pytest.fail("The production factory must never construct the lexical retriever")

    monkeypatch.setattr(lexical_module, "create_demo_company_policy_retriever", forbidden_lexical)
    workflow = workflow_module.get_job_description_workflow()
    retriever = workflow._retriever
    assert isinstance(retriever, SemanticCompanyPolicyRetriever)
    assert retriever._document_id == DOCUMENT_ID
    assert retriever._repository._session_factory is factory
    assert retriever._embedding_service is embedding
    assert retriever.retrieval_mode == "semantic_bge_pgvector"
    assert workflow._generator is generator
    assert workflow_module.get_job_description_workflow() is workflow


@pytest.mark.parametrize("failure_stage", ["embedding", "database", "document"])
def test_semantic_failure_returns_safe_502_without_generation_or_fallback(monkeypatch, failure_stage):
    configure(monkeypatch)
    monkeypatch.setattr(workflow_module, "create_database_engine", lambda _: object())
    monkeypatch.setattr(workflow_module, "create_database_session_factory", lambda _: object())

    class Embedding:
        def embed_query(self, query):
            if failure_stage == "embedding":
                raise RuntimeError("PRIVATE_MODEL_PATH_AND_POLICY")
            return (1.0,) + (0.0,) * 383

    class Repository:
        def __init__(self, factory):
            pass

        async def find_nearest_chunks(self, document_id, vector, *, top_k):
            if failure_stage == "document":
                raise PolicyRetrievalError("PRIVATE_DOCUMENT_UUID")
            raise RuntimeError("PRIVATE_DATABASE_URL_AND_SQL")

    class Generator:
        async def generate(self, *args):
            pytest.fail("Generation must not run after semantic retrieval failure")

    monkeypatch.setattr(workflow_module, "BGEEmbeddingService", Embedding)
    monkeypatch.setattr(workflow_module, "CompanyPolicyRepository", Repository)
    monkeypatch.setattr(workflow_module, "GroqJobDescriptionGenerator", lambda **_: Generator())
    response = asyncio.run(post_request())
    assert response.status_code == 502
    assert response.json() == job_descriptions.GENERATION_FAILURE_RESPONSE
    assert "PRIVATE" not in response.text


def test_policy_document_setting_is_validated_uuid():
    configuration = Settings(_env_file=None, company_policy_document_id=str(DOCUMENT_ID))
    assert configuration.company_policy_document_id == DOCUMENT_ID
    with pytest.raises(ValidationError):
        Settings(_env_file=None, company_policy_document_id="not-a-uuid")
