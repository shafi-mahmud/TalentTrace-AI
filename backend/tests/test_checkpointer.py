import asyncio
import importlib
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, ConfigurationError
from app.db import checkpointer as module
from app.db import setup_checkpointer as cli
from app.db.workflow_threads import WorkflowThread


URL = "postgresql://synthetic:PRIVATE_PASSWORD@localhost/talenttrace_checkpoints"
BUSINESS = "postgresql+asyncpg://synthetic:PRIVATE_PASSWORD@localhost/talenttrace"


def configuration(url=URL):
    return Settings(_env_file=None, database_url=BUSINESS, langgraph_checkpoint_database_url=url)


@pytest.mark.parametrize("url", [
    "sqlite:///PRIVATE_PASSWORD", "postgresql+asyncpg://synthetic:PRIVATE_PASSWORD@localhost/checkpoints",
    "postgresql://host", "postgresql://synthetic:PRIVATE_PASSWORD@localhost:bad/checkpoints",
    "postgresql://host/checkpoints?unknown=PRIVATE_PASSWORD", "not-a-url-PRIVATE_PASSWORD",
    "postgresql://host/checkpoints?service=PRIVATE_PASSWORD",
    "postgresql://host/checkpoints?dbname=talenttrace",
    "postgresql://host/talenttrace",
])
def test_invalid_or_business_checkpoint_url_is_safely_rejected(url):
    with pytest.raises(ConfigurationError) as error:
        configuration(url)
    assert "PRIVATE" not in str(error.value)
    assert url not in str(error.value)


def test_checkpoint_url_optional_and_secret():
    assert configuration(None).langgraph_checkpoint_database_url is None
    assert "PRIVATE_PASSWORD" not in repr(configuration())
    assert "PRIVATE_PASSWORD" not in configuration().model_dump_json()
    assert configuration().langgraph_checkpoint_database_url.get_secret_value() == URL


def test_missing_configuration_only_fails_when_invoked(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No connection should be attempted")
    monkeypatch.setattr(module.AsyncPostgresSaver, "from_conn_string", forbidden)
    async def run():
        async with module.open_checkpointer(configuration(None)):
            pytest.fail("A saver must not be yielded")
    with pytest.raises(module.CheckpointerError, match="not configured"):
        asyncio.run(run())


@pytest.mark.parametrize("action", ["open", "setup", "caller_error"])
def test_official_factory_strict_serializer_setup_and_resource_lifecycle(monkeypatch, action):
    calls = []
    class Saver:
        async def setup(self):
            calls.append("setup")
    saver = Saver()
    @asynccontextmanager
    async def factory(url, *, serde):
        assert url == URL
        assert serde.pickle_fallback is False
        assert serde._allowed_msgpack_modules is None
        assert serde._allowed_json_modules is None
        primitive = {"count": 1, "items": [True, None, "synthetic"]}
        assert serde.loads_typed(serde.dumps_typed(primitive)) == primitive
        calls.append("open")
        try:
            yield saver
        finally:
            calls.append("close")
    monkeypatch.setattr(module.AsyncPostgresSaver, "from_conn_string", factory)
    async def run():
        if action == "setup":
            await module.setup_checkpointer(configuration())
        else:
            async with module.open_checkpointer(configuration()) as value:
                assert value is saver
                if action == "caller_error":
                    raise LookupError("Caller failure")
    if action == "caller_error":
        with pytest.raises(LookupError):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert calls == (["open", "setup", "close"] if action == "setup" else ["open", "close"])


@pytest.mark.parametrize("stage", ["factory", "open", "setup", "close"])
def test_connection_setup_and_close_failures_are_sanitized(monkeypatch, stage):
    class Saver:
        async def setup(self):
            if stage == "setup":
                raise RuntimeError("PRIVATE_STATE_PASSWORD_SQL")
    @asynccontextmanager
    async def factory(*args, **kwargs):
        if stage == "open":
            raise RuntimeError(URL)
        try:
            yield Saver()
        finally:
            if stage == "close":
                raise RuntimeError(URL)
    monkeypatch.setattr(module.AsyncPostgresSaver, "from_conn_string", factory)
    if stage == "factory":
        def fail_factory(*args, **kwargs):
            raise RuntimeError(URL)
        monkeypatch.setattr(module.AsyncPostgresSaver, "from_conn_string", fail_factory)
    with pytest.raises(module.CheckpointerError) as error:
        asyncio.run(module.setup_checkpointer(configuration()))
    assert "PRIVATE" not in str(error.value)
    assert URL not in str(error.value)


def test_connection_open_deadline_is_controlled_and_cancels_attempt(monkeypatch):
    calls = []
    @asynccontextmanager
    async def delayed(*args, **kwargs):
        calls.append("opening")
        try:
            await asyncio.sleep(100)
            yield None
        finally:
            calls.append("cancelled")
    monkeypatch.setattr(module, "CONNECTION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module.AsyncPostgresSaver, "from_conn_string", delayed)
    async def run():
        async with module.open_checkpointer(configuration()):
            pytest.fail("Timed out connection must not be yielded")
    with pytest.raises(module.CheckpointerError, match="could not be opened"):
        asyncio.run(run())
    assert calls == ["opening", "cancelled"]


@pytest.mark.parametrize("failure", [False, True])
def test_setup_cli_safe_output(monkeypatch, capsys, failure):
    async def setup():
        print("PRIVATE_STATE_SQL")
        if failure:
            raise RuntimeError(URL)
    monkeypatch.setattr(module, "setup_checkpointer", setup)
    assert cli.main() == int(failure)
    result = capsys.readouterr()
    assert result.out == ("Checkpoint initialization failed. Check configuration and database availability.\n" if failure else "Checkpoint initialization succeeded.\n")
    assert not result.err


def test_strict_serializer_rejects_pickle_and_arbitrary_objects():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serializer = JsonPlusSerializer(allowed_msgpack_modules=None, pickle_fallback=False)
    with pytest.raises((TypeError, ValueError, NotImplementedError)):
        serializer.dumps_typed(object())
    with pytest.raises((TypeError, ValueError, NotImplementedError)):
        serializer.loads_typed(("pickle", b"unsafe-test-bytes"))


@pytest.mark.parametrize("kind", ["jd", "screening", "copilot", "evaluation"])
def test_known_opaque_thread_namespaces_are_stable(kind):
    identity = uuid4()
    thread = WorkflowThread(workflow_kind=kind, instance_id=identity)
    assert thread.thread_id == f"{kind}:{identity}"
    assert WorkflowThread.from_thread_id(thread.thread_id) == thread
    assert len(thread.thread_id) <= 47
    with pytest.raises(ValidationError):
        thread.instance_id = uuid4()


@pytest.mark.parametrize("value", ["master:00000000-0000-0000-0000-000000000000", "jd:private@example.test", "jd:name", "jd:phone:123", "jd:" + "x" * 80, "jd:12345678123412341234123456789012", None])
def test_malformed_thread_ids_are_rejected_without_echo(value):
    with pytest.raises(ValueError) as error:
        WorkflowThread.from_thread_id(value)
    assert "private" not in str(error.value)


def test_business_metadata_has_no_checkpoint_tables():
    from app.db.base import Base
    assert not {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}.intersection(Base.metadata.tables)


def test_import_and_health_are_lazy_even_without_checkpoint_configuration():
    code = '''
import asyncio, sys, httpx, psycopg
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected checkpoint activity')
psycopg.AsyncConnection.connect = forbidden
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
AsyncPostgresSaver.setup = forbidden
import app.core.config as config
config.settings = config.Settings(_env_file=None, database_url=None, langgraph_checkpoint_database_url=None)
import app.db.checkpointer
import app.db.setup_checkpointer
from app.main import app
async def run():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'service': 'talenttrace-api'}
asyncio.run(run())
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, env=dict(os.environ))
    assert result.returncode == 0, "Lazy import/health check failed; output withheld"
    assert not result.stdout and not result.stderr, "Unexpected output withheld"
