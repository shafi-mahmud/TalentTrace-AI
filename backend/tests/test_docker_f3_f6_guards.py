"""Offline guards only; no Docker or database access."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("container_lab", Path(__file__).resolve().parents[2] / "docker/f3_f6_container.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

@pytest.mark.parametrize("value", [None, "", "talenttrace-docker-demo", "tt-f3f6-test-../private", "tt-f3f6-test-abcdef"])
def test_invalid_project(value):
    with pytest.raises(RuntimeError): lab.validate_project(value)

def test_valid_project():
    assert lab.validate_project("tt-f3f6-test-012345abcdef")

@pytest.mark.parametrize("identity,consumed,populated", [
    (("preserved", "transcript_test",54402),False,False),
    (("transcript_test", "other",54402),False,False),
    (("transcript_test", "transcript_test",5432),False,False),
    (("transcript_test", "transcript_test",54402),True,False),
    (("transcript_test", "transcript_test",54402),False,True)])
def test_rejects_unsafe_database(identity,consumed,populated):
    with pytest.raises(RuntimeError): lab.require_fresh(identity,consumed,populated)

def test_fresh_database():
    lab.require_fresh(("transcript_test","transcript_test",54402),False,False)

@pytest.mark.parametrize("address", [("api.groq.com",443),("127.0.0.1",54402),("10.1.1.2",443),"/var/run/docker.sock",()])
def test_external_connection_denied(address):
    assert not lab.allowed_connection(address,{"10.1.1.2"})

def test_database_connection_allowed():
    assert lab.allowed_connection(("10.1.1.2",54402),{"10.1.1.2"})


def test_container_fixture_disabled_by_default(monkeypatch):
    monkeypatch.delenv("F3_F6_TEST_PROJECT", raising=False)
    with pytest.raises(pytest.skip.Exception):
        next(lab.pg.__wrapped__())


@pytest.mark.parametrize("heads", [[], ["0015_reviewer_confirmation"], ["0017_future"], [lab.REVIEWED_HEAD,"other"]])
def test_migration_contract_requires_review(monkeypatch, heads):
    from types import SimpleNamespace
    monkeypatch.setattr(lab.ScriptDirectory, "from_config", lambda cfg: SimpleNamespace(get_heads=lambda: heads))
    with pytest.raises(RuntimeError): lab.migration_head(None)


def test_actual_migration_head():
    cfg = lab.Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    cfg.set_main_option('script_location',str(Path(__file__).resolve().parents[1]/'alembic'))
    assert lab.migration_head(cfg) == '0016_submission_deletion'


def test_migration_failure_propagates(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    monkeypatch.setattr(lab,'migration_head',lambda cfg:lab.REVIEWED_HEAD)
    monkeypatch.setattr(lab.command,'upgrade',lambda cfg,head,sql:None)
    connection = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError('synthetic migration failure')),fetch=AsyncMock())
    with pytest.raises(RuntimeError,match='synthetic migration failure'):
        asyncio.run(lab.migrate_verified_database(connection,SimpleNamespace()))
    connection.fetch.assert_not_awaited()


@pytest.mark.parametrize("revisions", [[], [{'version_num':'0015_reviewer_confirmation'}], [{'version_num':lab.REVIEWED_HEAD},{'version_num':'other'}]])
def test_migrated_revision_must_match(monkeypatch,revisions):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    monkeypatch.setattr(lab,'migration_head',lambda cfg:lab.REVIEWED_HEAD)
    monkeypatch.setattr(lab.command,'upgrade',lambda cfg,head,sql:None)
    connection = SimpleNamespace(execute=AsyncMock(),fetch=AsyncMock(return_value=revisions))
    with pytest.raises(RuntimeError):
        asyncio.run(lab.migrate_verified_database(connection,SimpleNamespace()))
