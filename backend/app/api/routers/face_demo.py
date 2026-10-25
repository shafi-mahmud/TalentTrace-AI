"""Isolated, opt-in synthetic numeric demonstration; no image/camera/upload endpoint."""
from datetime import datetime,timezone
from typing import Annotated,Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,BeforeValidator,ConfigDict,field_validator
from sqlalchemy import select
from app.core.auth import current_recruiter,database_session,protect_mutation
from app.core.config import settings
from app.db.models.recruiter import InterviewInvitation
from app.api.routers.interview_access import candidate_session,owned_schedule
from app.services.livekit_interview import join_window
from app.services.face_demo import Binding,CONSENT_VERSION,CONSENT_WORDING,FaceDemoStore

router=APIRouter(tags=['Synthetic face demonstration'])
store=FaceDemoStore()
RunId=Annotated[UUID,BeforeValidator(lambda value:UUID(value) if isinstance(value,str) else value)]

class Consent(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    version:Literal['face-synthetic-demo-v1']
    decision:Literal['accept']
class Scope(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    run_id:RunId
class Review(Scope):
    review_confirmed:Literal[True]
    @field_validator('review_confirmed',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Explicit recruiter review is required.')
        return value
class Enrollment(Review):
    fixture:Literal['vector-a-reference','vector-b-reference']
class Comparison(Review):
    fixture:Literal['vector-a-probe','vector-b-probe']


def enabled(interview_id):
    if not settings.face_synthetic_demo_enabled:
        store.clear()
        raise HTTPException(404,'Synthetic face demo unavailable.')
    if interview_id not in settings.face_synthetic_demo_interview_ids:
        raise HTTPException(404,'Synthetic face demo unavailable.')


def binding(interview,invitation):
    return Binding(interview.recruiter_id,interview.job_id,interview.batch_id,interview.upload_id,
        interview.id,invitation.id,invitation.candidate_session_hash,interview.criteria_revision)


def window(interview):
    try:join_window(interview)
    except ValueError:
        store.remove(interview.id)
        raise HTTPException(409,'Interview unavailable.') from None


async def candidate_binding(request,db):
    invitation,interview=await candidate_session(request,db)
    enabled(interview.id);window(interview)
    return binding(interview,invitation)


async def recruiter_binding(db,user,job_id,interview_id):
    enabled(interview_id)
    interview=await owned_schedule(db,user,job_id,interview_id)
    window(interview)
    invitation=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==interview.id).execution_options(populate_existing=True))
    if (invitation is None or invitation.revoked or not invitation.candidate_session_hash
            or invitation.expires_at<=datetime.now(timezone.utc)):
        store.remove(interview.id)
        raise HTTPException(409,'Candidate access unavailable.')
    return binding(interview,invitation)


@router.get('/interview-access/face-demo/consent')
async def wording(request:Request,db=Depends(database_session)):
    await candidate_binding(request,db)
    return {'version':CONSENT_VERSION,'wording':CONSENT_WORDING,'real_biometrics_enabled':False}

@router.post('/interview-access/face-demo/consent')
async def consent(body:Consent,request:Request,db=Depends(database_session)):
    await protect_mutation(request)
    return store.consent(await candidate_binding(request,db))

@router.post('/interview-access/face-demo/withdraw')
async def withdraw(body:Scope,request:Request,db=Depends(database_session)):
    await protect_mutation(request)
    scope=await candidate_binding(request,db)
    store.checked(scope,body.run_id)
    store.remove(scope.interview_id,body.run_id)
    return {'state':'withdrawn'}

@router.post('/jobs/{job_id}/interviews/{interview_id}/face-demo/enroll')
async def enroll(job_id:UUID,interview_id:UUID,body:Enrollment,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await recruiter_binding(db,user,job_id,interview_id)
    return store.enroll(scope,body.run_id,body.fixture)

@router.post('/jobs/{job_id}/interviews/{interview_id}/face-demo/compare')
async def compare(job_id:UUID,interview_id:UUID,body:Comparison,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await recruiter_binding(db,user,job_id,interview_id)
    return store.compare(scope,body.run_id,body.fixture)

@router.get('/jobs/{job_id}/interviews/{interview_id}/face-demo/{run_id}')
async def result(job_id:UUID,interview_id:UUID,run_id:UUID,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await recruiter_binding(db,user,job_id,interview_id)
    return store.view(scope,run_id)

@router.post('/jobs/{job_id}/interviews/{interview_id}/face-demo/delete')
async def delete(job_id:UUID,interview_id:UUID,body:Scope,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await recruiter_binding(db,user,job_id,interview_id)
    store.checked(scope,body.run_id);store.remove(interview_id,body.run_id)
    return {'state':'deleted'}
