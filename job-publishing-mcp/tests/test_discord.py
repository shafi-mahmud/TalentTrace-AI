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


def test_application_url_has_compact_field_and_mentions_remain_disabled(job_data):
    url="https://docs.google.com/forms/d/e/synthetic-test-form/viewform"
    payload=format_payload(JobCircular(**job_data,application_url=url))
    fields = payload["embeds"][0]["fields"]
    reference = {"name": "Job Reference", "value": job_data["job_reference"], "inline": False}
    application = {"name": "Apply for this role", "value": url, "inline": False}
    assert reference in fields
    assert fields.index(reference) + 1 == fields.index(application)
    assert payload["allowed_mentions"]=={"parse":[],"users":[],"roles":[],"replied_user":False}


def test_absent_application_url_has_no_apply_field(job_data):
    payload=format_payload(JobCircular(**job_data))
    fields = payload["embeds"][0]["fields"]
    assert {"name": "Job Reference", "value": job_data["job_reference"], "inline": False} in fields
    assert not any(field["name"]=="Apply for this role" for field in fields)


def test_application_url_field_size_is_checked_before_any_http(job_data,settings):
    url="https://example.invalid/"+"a"*1100
    def forbidden(request): pytest.fail("Oversized URL must not reach Discord.")
    publisher=DiscordPublisher(settings,transport=httpx.MockTransport(forbidden))
    with pytest.raises(PublicationError,match="limits"):
        asyncio.run(publisher.publish(JobCircular(**job_data,application_url=url)))


def test_application_url_counts_toward_total_embed_limit(job_data):
    circular=JobCircular(**{**job_data,"summary":"x"*2900,"responsibilities":["r"*300]*3,"required_skills":["s"*100]*9,"preferred_skills":["p"*100]*9,"qualifications":["q"*150]})
    payload=format_payload(circular)
    embed=payload["embeds"][0]
    total=discord_length(embed["title"])+discord_length(embed["description"])+discord_length(embed["footer"]["text"])+sum(discord_length(f["name"])+discord_length(f["value"]) for f in embed["fields"])
    assert total<=6000
    url="https://example.invalid/"+"a"*500
    with pytest.raises(PublicationError,match="limits"):
        format_payload(JobCircular(**circular.model_dump(exclude={"application_url"}),application_url=url))


def test_application_link_publication_remains_once_and_metadata_only(job_data,settings):
    calls=[]
    url="https://forms.gle/synthetic-test"
    def handler(request):
        calls.append(request)
        assert any(field["value"]==url for field in json.loads(request.content)["embeds"][0]["fields"])
        return httpx.Response(200,json={"id":"123456789012345679"})
    result=asyncio.run(DiscordPublisher(settings,transport=httpx.MockTransport(handler)).publish(JobCircular(**job_data,application_url=url)))
    assert len(calls)==1
    assert set(result.model_dump())=={"destination","status","external_id"}
    assert url not in result.model_dump_json()
