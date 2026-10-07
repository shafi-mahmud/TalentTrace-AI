import socket

import httpx
import pytest

from talenttrace_job_publishing.config import Settings


# Entirely synthetic credentials: never read the developer's actual root .env.
SYNTHETIC_WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/" + "synthetic_token_" * 4


@pytest.fixture(autouse=True)
def isolate_configuration_and_network(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    def forbid_network(*args, **kwargs):
        raise AssertionError("Real network access is forbidden in automated tests.")

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        # Windows asyncio creates its internal socketpair over loopback.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return forbid_network()

    def guarded_connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect_ex(sock, address)
        return forbid_network()

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbid_network)


@pytest.fixture
def settings():
    return Settings(_env_file=None, discord_webhook_url=SYNTHETIC_WEBHOOK)


@pytest.fixture
def job_data():
    return {
        "title": " Backend AI Engineer ",
        "summary": "Build secure backend services.",
        "responsibilities": ["Develop APIs", "Write tests"],
        "required_skills": ["Python", "FastAPI"],
        "qualifications": ["Demonstrable engineering skills"],
    }
