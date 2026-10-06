import asyncio
from typing import Any

import httpx

from app.main import app


NOT_IMPLEMENTED_RESPONSE = {
    "code": "jd_generation_not_implemented",
    "message": "Job description generation is not implemented yet.",
}


def valid_request_data() -> dict[str, object]:
    return {
        "job_title": "Backend Engineer",
        "role_summary": "Build and maintain reliable backend services for TalentTrace AI.",
        "responsibilities": ["Develop well-tested FastAPI endpoints"],
        "required_skills": ["Python"],
    }


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


def test_valid_request_returns_fixed_not_implemented_response() -> None:
    response = asyncio.run(
        send_request(
            "POST",
            "/api/v1/job-descriptions/generate",
            json=valid_request_data(),
        )
    )

    assert response.status_code == 501
    assert response.json() == NOT_IMPLEMENTED_RESPONSE


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


def test_openapi_includes_job_description_generation_endpoint() -> None:
    response = asyncio.run(send_request("GET", "/openapi.json"))

    assert response.status_code == 200
    operations = response.json()["paths"]["/api/v1/job-descriptions/generate"]
    assert "post" in operations
