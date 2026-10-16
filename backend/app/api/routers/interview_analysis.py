"""Opt-in synthetic-only recruiter analysis; no model call on GET/navigation."""
from functools import lru_cache
import re
from uuid import UUID
from fastapi import APIRouter,Request,Header,HTTPException
from pydantic import BaseModel,ConfigDict
from app.core.config import settings
from app.services.evaluation_input import PostInterviewInputService,EvaluationInputError
from app.services.interview_transcripts import TranscriptError
from app.services.transcript_runtime import runtime
from app.services.interview_analysis import AnalysisManager,DISCLOSURE_VERSION,DISCLOSURE
from app.rag.technical_references import configured_retriever
from app.integrations.llm.interview_evaluation import GroqInterviewAssessment
from app.agents.evaluation.workflow import InterviewEvaluationWorkflow,AssessmentError

router=APIRouter(tags=['Synthetic interview analysis'])


def available():
    return bool(settings.environment=='development' and settings.interview_evaluation_enabled
        and settings.transcript_storage_enabled and settings.interview_evaluation_synthetic_job_ids and settings.groq_api_key)


@lru_cache(maxsize=1)
def manager():
    if not available():raise HTTPException(404,'Synthetic interview analysis is disabled.')
    provider=GroqInterviewAssessment(settings.groq_api_key.get_secret_value(),settings.llm_model)
    from app.services.durable_interview_analysis import DurableAnalysisManager
    manager_type=DurableAnalysisManager if settings.interview_evaluation_durable_enabled else AnalysisManager
    return manager_type(PostInterviewInputService(runtime().storage),
        InterviewEvaluationWorkflow(provider,configured_retriever(settings.technical_reference_model_path)),settings.interview_evaluation_synthetic_job_ids)


class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    retry_failed:bool=False
    expected_attempt:int|None=None


def safe(error):
    code=error.code if isinstance(error,TranscriptError) else str(error)
    # Only our fixed codes; no arbitrary exception/provider strings are exposed.
    if not re.fullmatch(r'[a-z_]{1,100}',code) or not code.startswith(('evaluation_','transcript_','storage_','owned_','qa_','capture_')):code='evaluation_unavailable'
    return HTTPException(409,{'code':code})


def active_manager():
    if not available():raise HTTPException(404,'Synthetic interview analysis is disabled.')
    return manager()


@router.get('/interview-analysis/config')
async def config():return {'enabled':available(),'version':DISCLOSURE_VERSION,'disclosure':DISCLOSURE,
    'persistence':'postgresql_privacy_bound' if settings.interview_evaluation_durable_enabled else 'ephemeral_single_worker'}


@router.post('/jobs/{job}/interviews/{interview}/analysis',status_code=202)
async def start(job:UUID,interview:UUID,body:Start,request:Request,
    revision:int=Header(alias='X-TalentTrace-Job-Revision',ge=1),
    disclosure:str=Header(alias='X-TalentTrace-Evaluation-Disclosure')):
    if disclosure!=DISCLOSURE_VERSION:raise HTTPException(403,'Review the synthetic external processing disclosure.')
    try:
        m=active_manager()
        if body.retry_failed:
            if not settings.interview_evaluation_durable_enabled:raise HTTPException(409,'Explicit durable retry is not enabled.')
            return await m.start(request,job,interview,revision,body.operation_id,True,body.expected_attempt)
        return await m.start(request,job,interview,revision,body.operation_id)
    except (TranscriptError,EvaluationInputError,AssessmentError) as error:raise safe(error) from None


@router.get('/jobs/{job}/interviews/{interview}/analysis/{operation_id}')
async def status(job:UUID,interview:UUID,operation_id:UUID,request:Request):
    try:return await active_manager().get(request,job,interview,operation_id)
    except (TranscriptError,EvaluationInputError,AssessmentError) as error:raise safe(error) from None
