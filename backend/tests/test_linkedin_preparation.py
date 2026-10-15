import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.routers import recruiter_chat as route
from app.core.auth import current_recruiter, database_session
from app.main import app
from app.schemas.job_publication import LinkedInPreparation
from app.integrations.job_publishing import mcp_client
from test_job_publication import job, setup_client


def test_mcp_client_uses_read_only_tool(monkeypatch, tmp_path):
    result = SimpleNamespace(is_error=False, structured_content={"destination": "linkedin", "status": "prepared", "mode": "manual", "announcement": "Synthetic job"})
    calls = setup_client(monkeypatch, tmp_path, result=result)
    from app.schemas.job_publication import RecruiterPublishRequest
    response = asyncio.run(mcp_client.MCPJobPublisher().prepare_linkedin(RecruiterPublishRequest(**job())))
    assert response.status == "prepared"
    assert calls[0][0] == "prepare_linkedin_job"
    assert len(calls) == 1


@pytest.mark.parametrize("authorized", [True, False])
def test_preparation_requires_owned_unchanged_draft(monkeypatch, authorized):
    calls = []
    async def authorize(*args):
        calls.append("authorize")
        if not authorized:
            raise HTTPException(409, "Draft changed.")
    async def prepare(request):
        calls.append("prepare")
        return LinkedInPreparation(destination="linkedin", status="prepared", mode="manual", announcement="Synthetic job")
    monkeypatch.setattr(route, "authorize_publication", authorize)
    monkeypatch.setattr(route, "get_job_publisher", lambda: SimpleNamespace(prepare_linkedin=prepare))
    async def user(): return SimpleNamespace(id=uuid4())
    async def database(): yield AsyncMock()
    previous = dict(app.dependency_overrides)
    app.dependency_overrides.update({current_recruiter: user, database_session: database})
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/recruiter-chat/linkedin/prepare", json=job())
    try:
        response = asyncio.run(check())
        assert response.status_code == (200 if authorized else 409)
        assert calls == (["authorize", "prepare"] if authorized else ["authorize"])
        if authorized: assert response.json()["status"] == "prepared"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_anonymous_preparation_rejected():
    async def database(): yield AsyncMock()
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[database_session] = database
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/recruiter-chat/linkedin/prepare", json=job())
            assert response.status_code in {401, 403}
    try:
        asyncio.run(check())
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_foreign_job_cannot_reach_preparation(monkeypatch):
    from app.schemas.job_publication import RecruiterPublishRequest
    async def reject(*args): raise HTTPException(404, "Job unavailable.")
    monkeypatch.setattr(route, "owned_job", reject)
    monkeypatch.setattr(route, "get_job_publisher", lambda: pytest.fail("Foreign job must not reach MCP."))
    request = RecruiterPublishRequest(**{**job(), "job_id": uuid4()})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(route.prepare_linkedin(request, SimpleNamespace(id=uuid4()), AsyncMock()))
    assert caught.value.status_code == 404


def test_failure_is_sanitized_and_never_retried(monkeypatch):
    calls = []
    async def authorize(*args): pass
    async def fail(request):
        calls.append(request)
        raise RuntimeError("PRIVATE_TOKEN")
    monkeypatch.setattr(route, "authorize_publication", authorize)
    monkeypatch.setattr(route, "get_job_publisher", lambda: SimpleNamespace(prepare_linkedin=fail))
    from app.schemas.job_publication import RecruiterPublishRequest
    response = asyncio.run(route.prepare_linkedin(RecruiterPublishRequest(**job()), SimpleNamespace(id=uuid4()), AsyncMock()))
    assert response.status_code == 502
    assert b"PRIVATE_TOKEN" not in response.body
    assert len(calls) == 1
