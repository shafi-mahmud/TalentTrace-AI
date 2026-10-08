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


router = APIRouter(prefix="/recruiter-chat", tags=["recruiter chat"])


@router.post("", response_model=RecruiterChatResponse, responses={
    502: {"description": "Interpretation or JD generation failed."},
    503: {"description": "Recruiter chat or JD generation is not configured."},
    504: {"description": "Interpretation or JD generation timed out."},
    409: {"description": "The bounded in-memory conversation expired or reached its limit."},
})
async def recruiter_chat(request: RecruiterChatRequest) -> RecruiterChatResponse | JSONResponse:
    try:
        return await RecruiterChatService(get_recruiter_interpreter()).respond(request)
    except ConversationUnavailableError:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={
            "code": "recruiter_conversation_unavailable",
            "message": "This conversation is no longer available. Start a new chat.",
        })
    except MissingGenerationConfigurationError:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={
            "code": "recruiter_chat_not_configured", "message": "Recruiter chat is not configured.",
        })
    except GenerationTimeoutError:
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content={
            "code": "recruiter_chat_timeout", "message": "Recruiter chat timed out. Please try again.",
        })
    except (GenerationProviderError, PolicyRetrievalError):
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "code": "recruiter_chat_failed", "message": "Recruiter chat could not be completed.",
        })
    except Exception:
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
