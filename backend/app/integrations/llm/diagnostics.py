"""Operational categories only: never log exception messages or provider bodies."""
import logging
import math
import re
from groq import APIConnectionError, APITimeoutError, APIStatusError, RateLimitError
from pydantic import ValidationError

logger = logging.getLogger("talenttrace.screening_diagnostics")


def rate_limit_metadata(error):
    """Whitelist operational numbers/labels; never return provider error text."""
    headers=getattr(getattr(error,"response",None),"headers",{})
    raw=headers.get("retry-after","")
    delay=float(raw) if re.fullmatch(r"\d{1,5}(?:\.\d{1,6})?",raw) else None
    if delay is not None and not math.isfinite(delay):delay=None
    body=getattr(error,"body",None)
    body=body.get("error",body) if isinstance(body,dict) else {}
    message=body.get("message","") if isinstance(body,dict) else ""
    found=re.search(r"\b(TPM|TPD|RPM|RPD)\b",message) if isinstance(message,str) else None
    limit=headers.get("x-ratelimit-limit-tokens","")
    return delay,found.group(1).lower() if found else "unknown",int(limit) if re.fullmatch(r"\d{1,9}",limit) else None


def provider_failure(stage, error):
    status = getattr(error, "status_code", None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    if isinstance(error, RateLimitError): category = "rate_limit"
    elif isinstance(error, APITimeoutError): category = "provider_timeout"
    elif isinstance(error, APIConnectionError): category = "provider_connection"
    elif isinstance(error, ValidationError): category = "structured_output_invalid"
    elif isinstance(error, APIStatusError):
        category = "provider_authentication" if status in {401,403} else "provider_server_error" if status and status >= 500 else "provider_request_rejected"
    else: category = "provider_or_response_failure"
    logger.warning("talenttrace_failure stage=%s category=%s exception_class=%s http_status=%s",
        stage, category, type(error).__name__, status)
    if isinstance(error,RateLimitError):
        delay,quota,limit=rate_limit_metadata(error)
        logger.warning("talenttrace_stage stage=%s category=rate_limit_metadata quota=%s retry_after_seconds=%s token_limit=%s",stage,quota,delay,limit)


def provider_usage(stage, response, elapsed):
    usage = getattr(response,"usage",None)
    def count(field):
        value=getattr(usage,field,None)
        return value if type(value) is int and 0 <= value <= 2**31-1 else None
    logger.info("talenttrace_stage stage=%s duration_ms=%s prompt_tokens=%s completion_tokens=%s",
        stage, int(elapsed*1000), count("prompt_tokens"), count("completion_tokens"))
