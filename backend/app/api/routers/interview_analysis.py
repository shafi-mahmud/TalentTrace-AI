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
from app.services.interview_mapping import SyntheticTechnicalRetriever
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
    return AnalysisManager(PostInterviewInputService(runtime().storage),
        InterviewEvaluationWorkflow(provider,SyntheticTechnicalRetriever()),settings.interview_evaluation_synthetic_job_ids)


class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID


def safe(error):
    code=error.code if isinstance(error,TranscriptError) else str(error)
    # Only our fixed codes; no arbitrary exception/provider strings are exposed.
    if not re.fullmatch(r'[a-z_]{1,100}',code) or not code.startswith(('evaluation_','transcript_','storage_','owned_','qa_','capture_')):code='evaluation_unavailable'
    return HTTPException(409,{'code':code})


def active_manager():
    if not available():raise HTTPException(404,'Synthetic interview analysis is disabled.')
    return manager()


@router.get('/interview-analysis/config')
async def config():return {'enabled':available(),'version':DISCLOSURE_VERSION,'disclosure':DISCLOSURE}


@router.post('/jobs/{job}/interviews/{interview}/analysis',status_code=202)
async def start(job:UUID,interview:UUID,body:Start,request:Request,
    revision:int=Header(alias='X-TalentTrace-Job-Revision',ge=1),
    disclosure:str=Header(alias='X-TalentTrace-Evaluation-Disclosure')):
    if disclosure!=DISCLOSURE_VERSION:raise HTTPException(403,'Review the synthetic external processing disclosure.')
    try:return await active_manager().start(request,job,interview,revision,body.operation_id)
    except (TranscriptError,EvaluationInputError,AssessmentError) as error:raise safe(error) from None


@router.get('/jobs/{job}/interviews/{interview}/analysis/{operation_id}')
async def status(job:UUID,interview:UUID,operation_id:UUID,request:Request):
    try:return await active_manager().get(request,job,interview,operation_id)
    except (TranscriptError,EvaluationInputError,AssessmentError) as error:raise safe(error) from None
