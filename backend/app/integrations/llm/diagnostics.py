"""Operational categories only: never log exception messages or provider bodies."""
import logging
from groq import APIConnectionError, APITimeoutError, APIStatusError, RateLimitError
from pydantic import ValidationError

logger = logging.getLogger("talenttrace.screening_diagnostics")


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


def provider_usage(stage, response, elapsed):
    usage = getattr(response,"usage",None)
    def count(field):
        value=getattr(usage,field,None)
        return value if type(value) is int and 0 <= value <= 2**31-1 else None
    logger.info("talenttrace_stage stage=%s duration_ms=%s prompt_tokens=%s completion_tokens=%s",
        stage, int(elapsed*1000), count("prompt_tokens"), count("completion_tokens"))
