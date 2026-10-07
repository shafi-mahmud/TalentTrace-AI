import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import importlib
from pathlib import Path
import httpx
import pytest
from app.api.routers import recruiter_chat as route
from app.main import app
from app.core.config import Settings
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
    assert calls == [{**job(), "work_arrangement": "onsite", "job_reference": "TT-JOB-30BB2CDF9A5CCCA9"}]


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


@pytest.fixture(autouse=True)
def isolate_application_configuration(monkeypatch):
    monkeypatch.setattr(mcp_client, "settings", Settings(_env_file=None, application_form_url=None))


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
    assert calls == [("publish_job", {"job": {**job(),"work_arrangement":"onsite","job_reference":"TT-JOB-30BB2CDF9A5CCCA9"}})]


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
    assert captured==[{**job(),"work_arrangement":"onsite","job_reference":"TT-JOB-30BB2CDF9A5CCCA9","application_url":None}]


@pytest.mark.parametrize("configured", [True, False])
def test_application_url_is_only_added_from_server_configuration(monkeypatch, tmp_path, configured):
    result=SimpleNamespace(is_error=False, structured_content={"destination":"discord","status":"published","external_id":"123456789012345678"})
    calls=setup_client(monkeypatch,tmp_path,result=result)
    url="https://docs.google.com/forms/d/e/synthetic-test-form/viewform" if configured else None
    configuration=Settings(_env_file=None, application_form_url=url)
    returned=asyncio.run(mcp_client.MCPJobPublisher(configuration).publish(RecruiterPublishRequest(**job())))
    sent=calls[0][1]["job"]
    assert sent.get("application_url")==url
    assert ("application_url" in sent)==configured
    assert set(returned.model_dump())=={"destination","status","external_id"}
    assert url is None or url not in returned.model_dump_json()


@pytest.mark.parametrize("field", ["application_url","application_form_url","APPLICATION_FORM_URL"])
def test_recruiter_or_generated_publication_payload_cannot_override_form(monkeypatch,field):
    monkeypatch.setattr(route,"get_job_publisher",lambda: pytest.fail("Client URL override must never reach MCP."))
    response=asyncio.run(send({**job(),field:"https://example.invalid/untrusted-form"}))
    assert response.status_code==422
    assert "untrusted-form" not in response.text


def test_failure_never_exposes_configured_application_url(monkeypatch,tmp_path):
    url="https://docs.google.com/forms/d/e/private-synthetic-test-form/viewform"
    calls=setup_client(monkeypatch,tmp_path,error=RuntimeError(url))
    configuration=Settings(_env_file=None,application_form_url=url)
    with pytest.raises(mcp_client.PublicationFailed) as error:
        asyncio.run(mcp_client.MCPJobPublisher(configuration).publish(RecruiterPublishRequest(**job())))
    assert url not in str(error.value)
    assert len(calls)==1


@pytest.mark.parametrize("configured", [True, False])
def test_env_file_to_endpoint_mcp_and_discord_application_link(monkeypatch, tmp_path, configured):
    """Exercise the complete local path; all external HTTP is replaced."""
    monkeypatch.delenv("APPLICATION_FORM_URL", raising=False)
    env_file = tmp_path / ".env"
    url = "https://example.com/apply"
    env_file.write_text(
        "APPLICATION_FORM_URL=" + url + "\n" if configured else "# No application form configured\n",
        encoding="utf-8",
    )
    configuration = Settings(_env_file=env_file)
    monkeypatch.setattr(mcp_client, "settings", configuration)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "job-publishing-mcp"))
    from talenttrace_job_publishing import server
    from talenttrace_job_publishing.config import Settings as PublishingSettings
    from talenttrace_job_publishing.publishers.discord import DiscordPublisher

    arguments_seen = []
    payloads_seen = []
    real_client = mcp_client.Client

    class CapturingClient(real_client):
        async def call_tool(self, name, arguments, **kwargs):
            arguments_seen.append(arguments)
            return await super().call_tool(name, arguments, **kwargs)

    def mocked_discord(request):
        import json
        payloads_seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "123456789012345678"})

    async def forbidden_http(*args, **kwargs):
        pytest.fail("Real Discord traffic must never occur.")

    publishing_settings = PublishingSettings(
        _env_file=None,
        discord_webhook_url="https://discord.com/api/webhooks/123456789012345678/" + "synthetic_token_" * 4,
    )
    monkeypatch.setattr(server, "load_settings", lambda: publishing_settings)
    monkeypatch.setattr(server, "DiscordPublisher", lambda settings: DiscordPublisher(
        settings, transport=httpx.MockTransport(mocked_discord),
    ))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden_http)
    monkeypatch.setattr(mcp_client, "Client", CapturingClient)
    monkeypatch.setattr(mcp_client, "stdio_client", lambda params, errlog: server.mcp)

    response = asyncio.run(send(job()))
    assert response.status_code == 200
    assert response.json() == {
        "destination": "discord", "status": "published", "external_id": "123456789012345678",
    }
    assert len(arguments_seen) == len(payloads_seen) == 1
    assert (configuration.application_form_url is not None) == configured
    assert ("application_url" in arguments_seen[0]["job"]) == configured
    fields = payloads_seen[0]["embeds"][0]["fields"]
    apply_fields = [field for field in fields if field["name"] == "Apply for this role"]
    reference = arguments_seen[0]["job"]["job_reference"]
    reference_field = {"name": "Job Reference", "value": reference, "inline": False}
    assert reference == "TT-JOB-30BB2CDF9A5CCCA9"
    assert reference_field in fields
    if configured:
        assert fields.index(reference_field) + 1 == fields.index(apply_fields[0])
    assert apply_fields == ([{"name": "Apply for this role", "value": url, "inline": False}] if configured else [])
    assert payloads_seen[0]["allowed_mentions"]["parse"] == []
    assert url not in response.text


def test_demo_reference_is_stable_for_normalized_content_and_changes_with_draft():
    original = RecruiterPublishRequest(**job()).mcp_job()["job_reference"]
    normalized = RecruiterPublishRequest(**{**job(), "title": "  " + job()["title"] + "  "})
    assert normalized.mcp_job()["job_reference"] == original
    revised = RecruiterPublishRequest(**{**job(), "summary": "A revised synthetic summary."})
    assert revised.mcp_job()["job_reference"] != original
    assert original == "TT-JOB-30BB2CDF9A5CCCA9"


def test_frontend_cannot_supply_job_reference(monkeypatch):
    monkeypatch.setattr(route, "get_job_publisher", lambda: pytest.fail("Reference override must be rejected."))
    response = asyncio.run(send({**job(), "job_reference": "ARBITRARY-REFERENCE"}))
    assert response.status_code == 422
    assert "ARBITRARY-REFERENCE" not in response.text


def test_llm_cannot_supply_job_reference():
    from pydantic import ValidationError
    from app.schemas.recruiter_chat import RecruiterInterpretation
    from test_recruiter_chat import extracted_data
    data = extracted_data()
    data["requirements"]["job_reference"] = "ARBITRARY-REFERENCE"
    with pytest.raises(ValidationError):
        RecruiterInterpretation.model_validate(data)
