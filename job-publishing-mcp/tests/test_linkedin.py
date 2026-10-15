import asyncio

from mcp import Client
import pytest

from talenttrace_job_publishing import server
from talenttrace_job_publishing.publishers.linkedin import LinkedInPublisher
from talenttrace_job_publishing.schemas import JobCircular


def test_preparation_formats_owned_job_without_network(job_data):
    job_data.update(location="Dhaka", employment_type="full_time", application_url="https://example.com/apply")
    result = LinkedInPublisher().prepare(JobCircular(**job_data))
    assert (result.destination, result.status, result.mode) == ("linkedin", "prepared", "manual")
    for value in ["Backend AI Engineer", "TT-JOB-0001", "Dhaka", "full time", "Python", "https://example.com/apply"]:
        assert value in result.announcement
    assert "external_id" not in result.model_dump()


@pytest.mark.parametrize("oauth_state", ["missing", "expired", "insufficient_permissions", "rate_limited", "provider_failure"])
def test_manual_mode_never_uses_oauth_or_provider(job_data, monkeypatch, oauth_state):
    # OAuth/provider scenarios cannot produce a false publication in manual mode.
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", oauth_state)
    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("prepare_linkedin_job", {"job": job_data})
            assert not result.is_error
            assert result.structured_content["status"] == "prepared"
            assert "external_id" not in result.structured_content
    asyncio.run(check())


def test_repeated_preparation_is_idempotent(job_data):
    adapter = LinkedInPublisher()
    job = JobCircular(**job_data)
    assert adapter.prepare(job) == adapter.prepare(job)


def test_read_only_tool_and_credential_rejection(job_data):
    async def check():
        async with Client(server.mcp) as client:
            tool = next(t for t in (await client.list_tools()).tools if t.name == "prepare_linkedin_job")
            assert tool.annotations.read_only_hint and tool.annotations.idempotent_hint
            result = await client.call_tool("prepare_linkedin_job", {"job": job_data, "token": "PRIVATE_TOKEN"})
            assert result.is_error
            assert "PRIVATE_TOKEN" not in result.model_dump_json()
    asyncio.run(check())


def test_overlong_preview_fails_without_echoing_content(job_data):
    job_data.update(title="x" * 200, summary="PRIVATE_CONTENT " * 190,
                    responsibilities=["x" * 300] * 15, required_skills=["x" * 100] * 20,
                    preferred_skills=["x" * 100] * 20, qualifications=["x" * 300] * 15,
                    application_url="https://example.com/" + "x" * 2000)
    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("prepare_linkedin_job", {"job": job_data})
            assert result.is_error
            assert "PRIVATE_CONTENT" not in result.model_dump_json()
    asyncio.run(check())
