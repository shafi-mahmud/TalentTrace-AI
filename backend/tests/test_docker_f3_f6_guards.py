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
