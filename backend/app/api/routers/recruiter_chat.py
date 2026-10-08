import logging
from uuid import uuid4

from app.integrations.job_publishing.mcp_client import get_job_publisher, PublicationUnavailable
from app.schemas.job_publication import PublicationResult, RecruiterPublishRequest

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.agents.jd.errors import (
    GenerationProviderError, GenerationTimeoutError, MissingGenerationConfigurationError,
)
from app.integrations.llm.recruiter_chat import get_recruiter_interpreter
from app.rag.retrieval import PolicyRetrievalError
from app.schemas.recruiter_chat import RecruiterChatRequest, RecruiterChatResponse
from app.services.recruiter_chat import ConversationUnavailableError, RecruiterChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recruiter-chat", tags=["recruiter chat"])


@router.post("", response_model=RecruiterChatResponse, responses={
    502: {"description": "Interpretation or JD generation failed."},
    503: {"description": "Recruiter chat or JD generation is not configured."},
    504: {"description": "Interpretation or JD generation timed out."},
    409: {"description": "The bounded in-memory conversation expired or reached its limit."},
})
async def recruiter_chat(request: RecruiterChatRequest) -> RecruiterChatResponse | JSONResponse:
    correlation_id = uuid4().hex[:12]
    try:
        return await RecruiterChatService(get_recruiter_interpreter()).respond(request, correlation_id=correlation_id)
    except ConversationUnavailableError as error:
        logger.warning("talenttrace_failure correlation_id=%s stage=api_response category=conversation_unavailable exception_class=%s", correlation_id, type(error).__name__)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={
            "code": "recruiter_conversation_unavailable",
            "message": "This conversation is no longer available. Start a new chat.",
        })
    except MissingGenerationConfigurationError as error:
        logger.warning("talenttrace_failure correlation_id=%s stage=api_response category=configuration_missing exception_class=%s", correlation_id, type(error).__name__)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={
            "code": "recruiter_chat_not_configured", "message": "Recruiter chat is not configured.",
        })
    except GenerationTimeoutError as error:
        logger.warning("talenttrace_failure correlation_id=%s stage=api_response category=provider_timeout exception_class=%s", correlation_id, type(error).__name__)
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content={
            "code": "recruiter_chat_timeout", "message": "Recruiter chat timed out. Please try again.",
        })
    except (GenerationProviderError, PolicyRetrievalError) as error:
        category = "policy_retrieval_failed" if isinstance(error, PolicyRetrievalError) else "provider_or_output_validation_failed"
        logger.warning("talenttrace_failure correlation_id=%s stage=api_response category=%s exception_class=%s", correlation_id, category, type(error).__name__)
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "code": "recruiter_chat_failed", "message": "Recruiter chat could not be completed.",
        })
    except Exception as error:
        logger.warning("talenttrace_failure correlation_id=%s stage=api_response category=unexpected_internal_error exception_class=%s", correlation_id, type(error).__name__)
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "code": "recruiter_chat_failed", "message": "Recruiter chat could not be completed.",
        })




@router.post("/publish", response_model=PublicationResult, responses={
    502: {"description": "Publication unconfirmed; check delivery before another attempt."},
    503: {"description": "Local MCP publishing server unavailable."},
})
async def publish_job(request: RecruiterPublishRequest) -> PublicationResult | JSONResponse:
    try:
        return await get_job_publisher().publish(request)
    except PublicationUnavailable:
        return JSONResponse(status_code=503, content={"code": "job_publication_unavailable", "message": "Job publishing is not configured."})
    except Exception:
        return JSONResponse(status_code=502, content={"code": "job_publication_unconfirmed", "message": "Publication was not confirmed. Check Discord before another attempt; delivery may have occurred."})
