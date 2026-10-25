import logging
import hashlib
import json
from uuid import uuid4

from app.integrations.job_publishing.mcp_client import get_job_publisher, PublicationUnavailable
from app.integrations.job_publishing.telegram import get_telegram_publisher, PublicationContentError
from app.schemas.job_publication import PublicationResult, RecruiterPublishRequest

from fastapi import APIRouter, status, Depends, HTTPException
from app.core.auth import current_recruiter, database_session
from app.services.recruiter_records import persist_chat, owned_job
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

@router.get("/providers")
async def providers(user=Depends(current_recruiter)):
    from app.integrations.llm.selection import provider_options
    return await provider_options()



@router.post("", response_model=RecruiterChatResponse, responses={
    502: {"description": "Interpretation or JD generation failed."},
    503: {"description": "Recruiter chat or JD generation is not configured."},
    504: {"description": "Interpretation or JD generation timed out."},
    409: {"description": "The bounded stored conversation expired or reached its limit."},
})
async def recruiter_chat(request: RecruiterChatRequest, user=Depends(current_recruiter), session=Depends(database_session)) -> RecruiterChatResponse | JSONResponse:
    correlation_id = uuid4().hex[:12]
    try:
        if request.ai_provider is None:
            service = RecruiterChatService(get_recruiter_interpreter())  # Existing legacy configured API contract.
        else:
            from app.integrations.llm.selection import selected_service
            service = await selected_service(request.ai_provider, request.external_processing_confirmed)
        return await persist_chat(session, user.id, request, service, correlation_id)
    except HTTPException:
        raise
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




# Bounded process-local delivery fence; restart/multiple workers need durable policy.
publication_attempts = {}

@router.post("/publish", response_model=PublicationResult, responses={
    502: {"description": "Publication unconfirmed; check delivery before another attempt."},
    503: {"description": "Local MCP publishing server unavailable."},
})
async def publish_job(request: RecruiterPublishRequest, user=Depends(current_recruiter), session=Depends(database_session)) -> PublicationResult | JSONResponse:
    await authorize_publication(session, user.id, request)
    key = (str(user.id), hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest())
    if key in publication_attempts:
        result = publication_attempts[key]
        if isinstance(result, PublicationResult):
            return result
        raise HTTPException(409, "Publication already attempted. Check delivery before another attempt.")
    if len(publication_attempts) >= 1000:
        raise HTTPException(503, "Publication capacity unavailable. Check delivery before another attempt.")
    publication_attempts[key] = 'pending'
    try:
        publisher = get_telegram_publisher() if request.destination == "telegram" else get_job_publisher()
        result = PublicationResult.model_validate(await publisher.publish(request))
        if result.destination != request.destination:
            raise ValueError("Publication destination mismatch.")
        publication_attempts[key] = result
        return result
    except PublicationContentError:
        publication_attempts.pop(key, None)
        return JSONResponse(status_code=422, content={"code": "job_publication_content_limit", "message": "Job exceeds destination limits. Shorten the saved draft first."})
    except PublicationUnavailable:
        publication_attempts.pop(key, None)
        return JSONResponse(status_code=503, content={"code": "job_publication_unavailable", "message": "Job publishing is not configured."})
    except Exception:
        publication_attempts[key] = "unconfirmed"
        return JSONResponse(status_code=502, content={"code": "job_publication_unconfirmed", "message": "Publication was not confirmed. Check the selected destination before another attempt; delivery may have occurred."})


async def authorize_publication(session, owner_id, request):
    if request.job_id is None:
        raise HTTPException(422, "Select a saved job draft before publishing.")
    job = await owned_job(session, owner_id, request.job_id)
    if job.draft is None:
        raise HTTPException(409, "This job has no generated draft.")
    # Compare the complete bounded content before any external side effect.
    from app.schemas.job_description import JobDescriptionGenerationResponse
    draft = JobDescriptionGenerationResponse.model_validate(job.draft).job_description
    for field in ("title", "summary", "responsibilities", "required_skills", "preferred_skills", "qualifications"):
        if getattr(request, field) != getattr(draft, field):
            raise HTTPException(409, "Draft changed. Reload it before publishing.")
    request._job_reference = job.job_reference
