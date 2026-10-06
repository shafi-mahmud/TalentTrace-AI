import asyncio
from typing import Any

import httpx
import pytest

from app.agents.jd.errors import (
    GenerationProviderError,
    GenerationTimeoutError,
    MissingGenerationConfigurationError,
)
from app.agents.jd.workflow import get_job_description_workflow
from app.agents.jd import workflow as workflow_module
from app.api.routers import job_descriptions
from app.main import app
from app.rag.retrieval import PolicyRetrievalError
from app.schemas.job_description import (
    GeneratedJobDescriptionDraft,
    JobDescriptionGenerationResponse,
    JobDescriptionGenerationRequest,
    PolicyGroundingCitation,
)


CITATION_ID = (
    "policy:12345678123456781234567812345678:1111111111111111:"
    "2222222222222222:0000"
)


def valid_request_data() -> dict[str, object]:
    return {
        "job_title": "Backend Engineer",
        "role_summary": "Build and maintain reliable backend services for TalentTrace AI.",
        "responsibilities": ["Develop well-tested FastAPI endpoints"],
        "required_skills": ["Python"],
    }


def successful_response() -> JobDescriptionGenerationResponse:
    return JobDescriptionGenerationResponse(
        model="openai/gpt-oss-120b",
        job_description=GeneratedJobDescriptionDraft(
            title="Backend Engineer",
            summary="Build reliable backend services using secure engineering practices.",
            responsibilities=["Develop well-tested FastAPI endpoints"],
            required_skills=["Python"],
            preferred_skills=[],
            qualifications=[
                "Relevant professional experience or equivalent learning"
            ],
            policy_citation_ids=[CITATION_ID],
        ),
        grounding_citations=[
            PolicyGroundingCitation(
                citation_id=CITATION_ID,
                source_title="Synthetic Endpoint Test Policy",
                heading_paths=(("Equal Opportunity",),),
            )
        ],
    )


class FakeWorkflow:
    def __init__(
        self,
        *,
        response: JobDescriptionGenerationResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error

    async def generate(
        self,
        _request: JobDescriptionGenerationRequest,
    ) -> JobDescriptionGenerationResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


@pytest.fixture(autouse=True)
def use_fake_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_descriptions,
        "get_job_description_workflow",
        lambda: FakeWorkflow(response=successful_response()),
    )


async def send_request(
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def test_valid_request_returns_structured_draft_with_grounding() -> None:
    response = asyncio.run(
        send_request(
            "POST",
            "/api/v1/job-descriptions/generate",
            json=valid_request_data(),
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["human_review_required"] is True
    assert body["retrieval_mode"] == "deterministic_lexical_demo"
    assert body["provider"] == "groq"
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["job_description"]["policy_citation_ids"] == [CITATION_ID]
    assert body["grounding_citations"][0]["citation_id"] == CITATION_ID


def test_invalid_request_returns_sanitized_validation_error() -> None:
    sensitive_text = "PRIVATE_RECRUITER_TEXT_" + ("x" * 150)
    data = valid_request_data()
    data["job_title"] = sensitive_text

    response = asyncio.run(
        send_request(
            "POST",
            "/api/v1/job-descriptions/generate",
            json=data,
        )
    )

    assert response.status_code == 422
    assert sensitive_text not in response.text
    assert "PRIVATE_RECRUITER_TEXT" not in response.text

    errors = response.json()["detail"]
    assert errors
    assert errors[0]["loc"] == ["body", "job_title"]
    assert set(errors[0]) == {"loc", "msg", "type"}


def test_undeclared_configuration_fields_are_rejected_without_echoing_values() -> None:
    sensitive_value = "DO_NOT_ECHO_INTERNAL_CONFIGURATION"
    data = valid_request_data()
    data.update(
        {
            "provider": sensitive_value,
            "model": sensitive_value,
            "api_key": sensitive_value,
            "prompt": sensitive_value,
            "system_instruction": sensitive_value,
            "configuration": sensitive_value,
        }
    )

    response = asyncio.run(
        send_request(
            "POST",
            "/api/v1/job-descriptions/generate",
            json=data,
        )
    )

    assert response.status_code == 422
    assert sensitive_value not in response.text

    error_locations = {tuple(error["loc"]) for error in response.json()["detail"]}
    for field_name in (
        "provider",
        "model",
        "api_key",
        "prompt",
        "system_instruction",
        "configuration",
    ):
        assert ("body", field_name) in error_locations


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            MissingGenerationConfigurationError("PRIVATE_KEY_MISSING_DETAIL"),
            503,
            "jd_generation_not_configured",
        ),
        (
            GenerationTimeoutError("PRIVATE_TIMEOUT_DETAIL"),
            504,
            "jd_generation_timeout",
        ),
        (
            GenerationProviderError("PRIVATE_PROVIDER_RESPONSE_AND_POLICY_TEXT"),
            502,
            "jd_generation_failed",
        ),
    ],
)
def test_generation_failures_are_sanitized(
    error: Exception,
    expected_status: int,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        job_descriptions,
        "get_job_description_workflow",
        lambda: FakeWorkflow(error=error),
    )

    response = asyncio.run(
        send_request(
            "POST",
            "/api/v1/job-descriptions/generate",
            json=valid_request_data(),
        )
    )

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert "PRIVATE" not in response.text
    assert "policy" not in response.text.casefold()


def test_policy_loading_failure_is_sanitized_before_workflow_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_details = r"PRIVATE_POLICY_DETAIL D:\private\company-policy.md"

    def fail_policy_loading() -> None:
        raise PolicyRetrievalError(private_details)

    monkeypatch.setattr(
        workflow_module, "create_demo_company_policy_retriever", fail_policy_loading
    )
    monkeypatch.setattr(
        job_descriptions, "get_job_description_workflow", get_job_description_workflow
    )
    get_job_description_workflow.cache_clear()
    try:
        response = asyncio.run(
            send_request(
                "POST",
                "/api/v1/job-descriptions/generate",
                json=valid_request_data(),
            )
        )
    finally:
        get_job_description_workflow.cache_clear()

    assert response.status_code == 502
    assert response.json() == {
        "code": "jd_generation_failed",
        "message": "Job description generation could not be completed.",
    }
    assert "PRIVATE" not in response.text
    assert "company-policy.md" not in response.text
    assert "private" not in response.text


def test_openapi_includes_job_description_generation_endpoint() -> None:
    response = asyncio.run(send_request("GET", "/openapi.json"))

    assert response.status_code == 200
    operations = response.json()["paths"]["/api/v1/job-descriptions/generate"]
    assert "post" in operations
    assert "200" in operations["post"]["responses"]
