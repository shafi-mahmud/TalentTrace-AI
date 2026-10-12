"""Bounded 429 recovery never retries validation, timeouts or unknown outcomes."""
import asyncio
from types import SimpleNamespace
import httpx
import pytest
from groq import RateLimitError, BadRequestError, APITimeoutError
from app.integrations.llm import screening_provider as provider


def limited(delay=None,quota="TPM"):
    headers={} if delay is None else {"Retry-After":delay,"x-ratelimit-limit-tokens":"8000"}
    return RateLimitError("PRIVATE",response=httpx.Response(429,headers=headers,request=httpx.Request("POST","https://example.test")),
        body={"message":f"PRIVATE credentials rate limit {quota}"})


def run(outcomes,monkeypatch):
    calls=[];waits=[]
    async def create(**kwargs):
        calls.append(kwargs)
        value=outcomes[len(calls)-1]
        if isinstance(value,Exception):raise value
        return value
    async def sleep(delay):waits.append(delay)
    monkeypatch.setattr(provider.asyncio,"sleep",sleep)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client,calls,waits


def test_explicit_short_reset_retries_once_with_same_contract(monkeypatch,caplog):
    client,calls,waits=run([limited("2.2"),"valid-response"],monkeypatch)
    result=asyncio.run(provider.screening_completion(client,"semantic_matching_provider",model="synthetic-model",response_format={"strict":True}))
    assert result=="valid-response" and len(calls)==2 and calls[0]==calls[1] and waits==[4]
    assert "rate_limit_backoff" in caplog.text and "PRIVATE" not in caplog.text


@pytest.mark.parametrize("error",[limited(),limited("3600"),limited("1","TPD"),limited("1","RPD"),limited("NaN"),limited("-1"),
    BadRequestError("PRIVATE",response=httpx.Response(400,request=httpx.Request("POST","https://example.test")),body="PRIVATE"),
    APITimeoutError(request=httpx.Request("POST","https://example.test")),ValueError("PRIVATE validation")])
def test_non_transient_unknown_or_unsafe_errors_not_retried(error,monkeypatch):
    client,calls,waits=run([error],monkeypatch)
    with pytest.raises(type(error)):asyncio.run(provider.screening_completion(client,"candidate_profile_provider"))
    assert len(calls)==1 and not waits


def test_third_rate_limit_is_final_failure(monkeypatch):
    client,calls,waits=run([limited("0"),limited("0"),limited("0")],monkeypatch)
    with pytest.raises(RateLimitError):asyncio.run(provider.screening_completion(client,"candidate_profile_provider"))
    assert len(calls)==3 and waits==[2,4]


def test_second_retry_can_recover_transient_rejection(monkeypatch):
    client,calls,waits=run([limited("0"),limited("1"),"validated"],monkeypatch)
    assert asyncio.run(provider.screening_completion(client,"candidate_profile_provider"))=="validated"
    assert len(calls)==3 and waits==[2,4]


def test_total_wait_budget_is_bounded(monkeypatch):
    client,calls,waits=run([limited("58"),limited("3")],monkeypatch)
    with pytest.raises(RateLimitError):asyncio.run(provider.screening_completion(client,"candidate_profile_provider"))
    assert len(calls)==2 and waits==[59]


def test_cancelled_backoff_propagates(monkeypatch):
    client,calls,_=run([limited("1")],monkeypatch)
    async def cancel(_):raise asyncio.CancelledError()
    monkeypatch.setattr(provider.asyncio,"sleep",cancel)
    with pytest.raises(asyncio.CancelledError):asyncio.run(provider.screening_completion(client,"candidate_profile_provider"))
    assert len(calls)==1
