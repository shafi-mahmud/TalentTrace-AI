import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import importlib
from pathlib import Path
import httpx
import pytest
from app.api.routers import recruiter_chat as route
from app.main import app
from app.integrations.job_publishing import mcp_client
from app.schemas.job_publication import PublicationResult, RecruiterPublishRequest


def job():
    return {"title": "Synthetic demo - NOT A REAL VACANCY", "summary": "Synthetic backend engineering demonstration only.",
        "responsibilities": ["Build APIs"], "required_skills": ["Python"], "preferred_skills": ["Docker"],
        "qualifications": ["Python experience"], "location": "Dhaka", "employment_type": "full_time", "work_arrangement": "on_site"}


async def send(data):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/recruiter-chat/publish", json=data)


def test_endpoint_returns_only_safe_confirmed_metadata(monkeypatch):
    calls = []
    class Publisher:
        async def publish(self, request):
            calls.append(request.mcp_job())
            return PublicationResult(destination="discord", status="published", external_id="123456789012345678")
    monkeypatch.setattr(route, "get_job_publisher", lambda: Publisher())
    response = asyncio.run(send(job()))
    assert response.status_code == 200
    assert response.json() == {"destination": "discord", "status": "published", "external_id": "123456789012345678"}
    assert calls == [{**job(), "work_arrangement": "onsite"}]


@pytest.mark.parametrize("changes", [
    {"title": ""}, {"title": "x" * 201}, {"summary": "PRIVATE_CONTENT\x00"},
    {"required_skills": ["x"] * 21}, {"responsibilities": ["x"] * 16},
    {"title": "<script>PRIVATE_CONTENT</script>"}, {"api_key": "PRIVATE_CONTENT"},
    {"webhook_url": "PRIVATE_CONTENT"}, {"work_arrangement": "onsite"},
    {"employment_type": "wrong"}, {"qualifications": []}, {"required_skills": "PRIVATE_CONTENT"},
])
def test_validation_prevents_mcp_and_never_echoes_input(monkeypatch, changes):
    monkeypatch.setattr(route, "get_job_publisher", lambda: pytest.fail("Invalid requests must not construct a publisher."))
    response = asyncio.run(send({**job(), **changes}))
    assert response.status_code == 422
    assert "PRIVATE_CONTENT" not in response.text


@pytest.mark.parametrize("error,status", [(RuntimeError("PRIVATE_WEBHOOK_PATH"),502), (TimeoutError("PRIVATE_CONTENT"),502), (mcp_client.PublicationUnavailable("PRIVATE_PATH"),503)])
def test_failures_are_sanitized_and_not_retried(monkeypatch, error, status):
    calls=[]
    class Publisher:
        async def publish(self, request):
            calls.append(request)
            raise error
    monkeypatch.setattr(route, "get_job_publisher", lambda: Publisher())
    response=asyncio.run(send(job()))
    assert response.status_code == status
    assert len(calls) == 1
    assert "PRIVATE" not in response.text


def setup_client(monkeypatch, tmp_path, result=None, error=None):
    executable=tmp_path / "job-publishing-mcp/.venv" / ("Scripts/python.exe" if mcp_client.os.name == "nt" else "bin/python")
    executable.parent.mkdir(parents=True)
    executable.touch()
    server=tmp_path / "job-publishing-mcp/talenttrace_job_publishing/server.py"
    server.parent.mkdir(parents=True)
    server.touch()
    monkeypatch.setattr(mcp_client, "REPOSITORY_ROOT", tmp_path)
    calls=[]
    def stdio(params, errlog):
        assert params.command == str(executable)
        assert params.args == ["-B", "-m", "talenttrace_job_publishing.server"]
        return "fake transport"
    class Client:
        def __init__(self, transport, **kwargs):
            assert transport == "fake transport"
            assert kwargs == {"read_timeout_seconds":30}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def call_tool(self, name, arguments):
            calls.append((name,arguments))
            if error: raise error
            return result
    monkeypatch.setattr(mcp_client, "stdio_client", stdio)
    monkeypatch.setattr(mcp_client, "Client", Client)
    return calls


def test_official_client_path_maps_job_and_invokes_tool_exactly_once(monkeypatch, tmp_path):
    result=SimpleNamespace(is_error=False, structured_content={"destination":"discord","status":"published","external_id":"123456789012345678"})
    calls=setup_client(monkeypatch,tmp_path,result=result)
    response=asyncio.run(mcp_client.MCPJobPublisher().publish(RecruiterPublishRequest(**job())))
    assert response.external_id == "123456789012345678"
    assert calls == [("publish_job", {"job": {**job(),"work_arrangement":"onsite"}})]


@pytest.mark.parametrize("result,error", [
    (SimpleNamespace(is_error=True, structured_content=None),None),
    (SimpleNamespace(is_error=False, structured_content={"status":"PRIVATE_CONTENT"}),None),
    (None,RuntimeError("PRIVATE_WEBHOOK_PATH")), (None,TimeoutError("PRIVATE_CONTENT")),
])
def test_client_tool_transport_timeout_and_malformed_results_are_safe(monkeypatch,tmp_path,result,error):
    calls=setup_client(monkeypatch,tmp_path,result=result,error=error)
    with pytest.raises(mcp_client.PublicationFailed) as caught:
        asyncio.run(mcp_client.MCPJobPublisher().publish(RecruiterPublishRequest(**job())))
    assert "PRIVATE" not in str(caught.value)
    assert len(calls)==1


def test_absent_local_server_fails_without_starting_transport(monkeypatch,tmp_path):
    monkeypatch.setattr(mcp_client,"REPOSITORY_ROOT",tmp_path)
    monkeypatch.setattr(mcp_client,"Client",lambda *a,**k: pytest.fail("No transport should start."))
    with pytest.raises(mcp_client.PublicationUnavailable):
        asyncio.run(mcp_client.MCPJobPublisher().publish(RecruiterPublishRequest(**job())))


def test_mapping_is_accepted_by_existing_standalone_contract(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"job-publishing-mcp"))
    module=importlib.import_module("talenttrace_job_publishing.schemas")
    value=module.JobCircular.model_validate(RecruiterPublishRequest(**job()).mcp_job())
    assert value.work_arrangement == "onsite"
    assert value.qualifications == job()["qualifications"]


def test_real_sdk_and_existing_server_tool_through_endpoint_without_discord(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"job-publishing-mcp"))
    from talenttrace_job_publishing import server
    from talenttrace_job_publishing.schemas import PublishJobResult
    captured=[]
    class SyntheticPublisher:
        async def publish(self, circular):
            captured.append(circular.model_dump(mode="json"))
            return PublishJobResult(external_id="123456789012345678")
    monkeypatch.setattr(server,"load_settings",lambda: object())
    monkeypatch.setattr(server,"DiscordPublisher",lambda settings: SyntheticPublisher())
    async def forbidden_http(*args,**kwargs):
        pytest.fail("Automated verification must not send external HTTP requests.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport,"handle_async_request",forbidden_http)
    # The official Client uses an in-process MCP transport for this protocol test.
    # Production retains its fixed stdio server executable, checked separately.
    monkeypatch.setattr(mcp_client,"stdio_client",lambda params,errlog: server.mcp)
    response=asyncio.run(send(job()))
    assert response.status_code==200
    assert response.json()=={"destination":"discord","status":"published","external_id":"123456789012345678"}
    assert captured==[{**job(),"work_arrangement":"onsite"}]
