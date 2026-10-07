import asyncio
import json
import logging

import httpx
import pytest

from conftest import SYNTHETIC_WEBHOOK
from talenttrace_job_publishing.publishers.discord import DiscordPublisher, PublicationError, discord_length, format_payload
from talenttrace_job_publishing.schemas import JobCircular


def test_bounded_payload_and_mentions_disabled(job_data):
    job_data["summary"] = "Job includes @everyone and @here as ordinary text."
    payload = format_payload(JobCircular(**job_data, preferred_skills=["SQL"], location="Dhaka"))
    assert payload["allowed_mentions"] == {"parse": [], "users": [], "roles": [], "replied_user": False}
    embed = payload["embeds"][0]
    assert embed["title"] == "Backend AI Engineer"
    assert all(discord_length(field["value"]) <= 1024 for field in embed["fields"])
    assert "SQL" in json.dumps(payload)


@pytest.mark.parametrize("oversize", ["section", "total", "unicode"])
def test_oversize_rejected_before_http(job_data, settings, oversize):
    if oversize == "section":
        job_data["responsibilities"] = ["x" * 300] * 4
    elif oversize == "unicode":
        job_data["responsibilities"] = ["😀" * 300] * 2
    else:
        job_data["summary"] = "x" * 3000
        job_data["responsibilities"] = ["x" * 300] * 3
        job_data["required_skills"] = ["x" * 100] * 9
        job_data["preferred_skills"] = ["x" * 100] * 9
        job_data["qualifications"] = ["x" * 300] * 3

    def unexpected_http(request):
        pytest.fail("Oversized payload must not reach HTTP.")

    publisher = DiscordPublisher(settings, transport=httpx.MockTransport(unexpected_http))
    with pytest.raises(PublicationError, match="limits"):
        asyncio.run(publisher.publish(JobCircular(**job_data)))


def test_success_returns_only_safe_metadata(job_data, settings, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["wait"] == "true"
        assert json.loads(request.content)["allowed_mentions"]["parse"] == []
        assert request.extensions["timeout"]["connect"] == 5.0
        assert request.extensions["timeout"]["read"] == 15.0
        return httpx.Response(200, json={"id": "123456789012345679", "content": "ignored", "secret": SYNTHETIC_WEBHOOK})

    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(DiscordPublisher(settings, transport=httpx.MockTransport(handler)).publish(JobCircular(**job_data)))
    assert result.model_dump() == {"destination": "discord", "status": "published", "external_id": "123456789012345679"}
    assert len(calls) == 1
    assert SYNTHETIC_WEBHOOK not in caplog.text
    assert SYNTHETIC_WEBHOOK not in repr(result)


@pytest.mark.parametrize("status", [301, 400, 401, 403, 429, 500])
def test_http_failure_is_safe_and_not_retried(job_data, settings, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=SYNTHETIC_WEBHOOK, headers={"Location": "https://example.com"})

    with pytest.raises(PublicationError) as error:
        asyncio.run(DiscordPublisher(settings, transport=httpx.MockTransport(handler)).publish(JobCircular(**job_data)))
    assert len(calls) == 1
    assert SYNTHETIC_WEBHOOK not in str(error.value)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_error_is_safe_and_not_retried(job_data, settings, failure):
    calls = []

    def handler(request):
        calls.append(request)
        raise failure(SYNTHETIC_WEBHOOK, request=request)

    with pytest.raises(PublicationError) as error:
        asyncio.run(DiscordPublisher(settings, transport=httpx.MockTransport(handler)).publish(JobCircular(**job_data)))
    assert len(calls) == 1
    assert SYNTHETIC_WEBHOOK not in str(error.value)
    assert "retrying" in str(error.value)


@pytest.mark.parametrize("data", [{}, {"id": "unsafe-secret"}, {"id": 123}, ["not a message"]])
def test_unconfirmed_provider_metadata_is_safe(job_data, settings, data):
    with pytest.raises(PublicationError, match="confirmed"):
        asyncio.run(DiscordPublisher(settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))).publish(JobCircular(**job_data)))
