import asyncio

import httpx
import pytest
from mcp import Client

from conftest import SYNTHETIC_WEBHOOK
from talenttrace_job_publishing import server
from talenttrace_job_publishing.config import Settings
from talenttrace_job_publishing.publishers.discord import DiscordPublisher


def test_tools_list_has_one_business_tool_and_typed_schemas():
    async def check():
        async with Client(server.mcp) as client:
            tools = (await client.list_tools()).tools
        assert [tool.name for tool in tools] == ["publish_job"]
        schema = tools[0].input_schema
        assert set(schema["properties"]) == {"job"}
        job_schema = schema["$defs"]["JobCircular"] if "$defs" in schema else schema["properties"]["job"]
        assert job_schema["additionalProperties"] is False
        assert "required_skills" in job_schema["required"]
        assert tools[0].output_schema is not None
        assert tools[0].annotations.idempotent_hint is False
    asyncio.run(check())


def test_mocked_publish_through_protocol(job_data, settings, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "123456789012345679"})

    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(server, "DiscordPublisher", lambda config: DiscordPublisher(config, transport=httpx.MockTransport(handler)))

    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("publish_job", {"job": job_data})
        assert result.is_error is False
        assert result.structured_content == {"destination": "discord", "status": "published", "external_id": "123456789012345679"}
        assert SYNTHETIC_WEBHOOK not in result.model_dump_json()
    asyncio.run(check())
    assert len(calls) == 1


def test_missing_config_through_protocol_is_safe(job_data, monkeypatch):
    monkeypatch.setattr(server, "load_settings", lambda: Settings(_env_file=None))

    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("publish_job", {"job": job_data})
        assert result.is_error is True
        assert "not configured" in result.content[0].text
        assert result.structured_content is None
    asyncio.run(check())


@pytest.mark.parametrize("extra_location", ["job", "arguments"])
def test_credential_arguments_are_rejected_safely(job_data, extra_location):
    arguments = {"job": job_data}
    if extra_location == "job":
        job_data["webhook_url"] = SYNTHETIC_WEBHOOK
    else:
        arguments["webhook_url"] = SYNTHETIC_WEBHOOK

    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("publish_job", arguments)
        assert result.is_error is True
        assert SYNTHETIC_WEBHOOK not in result.model_dump_json()
        assert "Invalid job circular" in result.content[0].text
    asyncio.run(check())


def test_provider_failure_through_protocol_is_safe(job_data, settings, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout(SYNTHETIC_WEBHOOK, request=request)

    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(server, "DiscordPublisher", lambda config: DiscordPublisher(config, transport=httpx.MockTransport(handler)))

    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("publish_job", {"job": job_data})
        assert result.is_error is True
        assert "timed out" in result.content[0].text
        assert SYNTHETIC_WEBHOOK not in result.model_dump_json()
    asyncio.run(check())


def test_invalid_job_text_is_not_echoed(job_data):
    job_data["summary"] = "private submitted job content\x00"

    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool("publish_job", {"job": job_data})
        assert result.is_error is True
        assert "private submitted" not in result.model_dump_json()
    asyncio.run(check())


def test_import_does_not_load_configuration(monkeypatch):
    import importlib

    def unexpected_load():
        pytest.fail("Server import must not load publishing configuration.")

    # Reloading the server imports this function but must not call it.
    from talenttrace_job_publishing import config
    with monkeypatch.context() as isolated:
        isolated.setattr(config, "load_settings", unexpected_load)
        reloaded = importlib.reload(server)
        assert reloaded.mcp is not None
    importlib.reload(server)


def test_real_stdio_tool_discovery_without_publication():
    import os
    from pathlib import Path
    import sys
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "talenttrace_job_publishing.server"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={"DISCORD_WEBHOOK_URL": "intentionally_invalid_test_configuration"},
    )

    async def check():
        with open(os.devnull, "w", encoding="utf-8") as diagnostics:
            async with Client(stdio_client(params, errlog=diagnostics), read_timeout_seconds=15) as client:
                result = await client.list_tools()
                assert [tool.name for tool in result.tools] == ["publish_job"]
                # Deliberately never call publish_job across the subprocess boundary.
    asyncio.run(check())
