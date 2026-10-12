"""Diagnostic regressions must never expose exception bodies or candidate input."""
import asyncio
import logging
from types import SimpleNamespace

import httpx
import pytest
from groq import RateLimitError, BadRequestError, InternalServerError, APITimeoutError
from app.integrations.llm.diagnostics import provider_failure, provider_usage
from app.integrations.llm.candidate_profile import GroqCandidateProfileExtractor, CandidateProviderError
from app.core.config import Settings
from test_candidate_profile import source_document
from app.services.candidate_profile import grounded, CandidateEvidenceError
from app.schemas.candidate_profile import EvidenceValue

PRIVATE="PRIVATE_PROVIDER_BODY_API_KEY_CV_TEXT"


@pytest.mark.parametrize("kind,status,category",[(RateLimitError,429,"rate_limit"),
    (BadRequestError,400,"provider_request_rejected"),(InternalServerError,503,"provider_server_error")])
def test_provider_http_categories_without_body(caplog,kind,status,category):
    response=httpx.Response(status,request=httpx.Request("POST","https://example.test/private"))
    error=kind(PRIVATE,response=response,body={"message":PRIVATE})
    provider_failure("candidate_profile_provider",error)
    assert f"category={category}" in caplog.text and f"http_status={status}" in caplog.text
    assert PRIVATE not in caplog.text and "example.test" not in caplog.text


def test_timeout_category_is_distinct(caplog):
    error=APITimeoutError(request=httpx.Request("POST","https://example.test/private"))
    provider_failure("semantic_matching_provider",error)
    assert "category=provider_timeout" in caplog.text and "example.test" not in caplog.text


def test_only_numeric_usage_is_logged(caplog):
    caplog.set_level(logging.INFO,logger="talenttrace.screening_diagnostics")
    provider_usage("candidate_profile_provider",SimpleNamespace(usage=SimpleNamespace(prompt_tokens=PRIVATE,completion_tokens=18)),.125)
    assert "duration_ms=125" in caplog.text and "completion_tokens=18" in caplog.text
    assert PRIVATE not in caplog.text


def test_profile_failure_stays_sanitized_and_single_attempt(caplog):
    calls=[]
    class Client:
        def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def create(self,**kwargs):
            calls.append(1)
            raise RateLimitError(PRIVATE,response=httpx.Response(429,request=httpx.Request("POST","https://example.test")),body=PRIVATE)
    with pytest.raises(CandidateProviderError) as failure:
        asyncio.run(GroqCandidateProfileExtractor(Settings(_env_file=None,groq_api_key="synthetic-key"),client_factory=Client).extract(source_document()))
    assert calls==[1] and "rate_limit" in caplog.text
    assert PRIVATE not in caplog.text and PRIVATE not in str(failure.value)


@pytest.mark.parametrize("evidence,value,code",[("invented quote","Python","quote_not_in_source"),("Python","invented value","value_not_in_quote")])
def test_evidence_reason_is_safe_without_relaxing_grounding(evidence,value,code):
    document=source_document("Python")
    with pytest.raises(CandidateEvidenceError) as failure:
        grounded(EvidenceValue(value=value,evidence=evidence,source_id="page:1"),{u.source_id:u for u in document.units})
    assert failure.value.code==code and "invented" not in str(failure.value)
