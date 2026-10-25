"""Synthetic-only online enrollment and separately authorized physical-viva comparison."""
from functools import wraps
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,SecretStr,field_validator
from sqlalchemy import select
from app.core.auth import current_recruiter,database_session,protect_mutation
from app.core.config import settings
from app.db.models.recruiter import InterviewInvitation
from app.api.routers.interview_access import candidate_session,owned_schedule
from app.api.routers.face_demo import binding,window,RunId
from app.services import face_workflow as runtime
from app.services.face_vault import VaultError,VERSION,WORDING

router=APIRouter(tags=['Synthetic enrollment and viva'])
class Consent(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    version:Literal['synthetic-face-workflow-v1']
    accepted:Literal[True]
    @field_validator('accepted',mode='before')
    @classmethod
    def explicit(cls,v):
        if v is not True:raise ValueError('Explicit consent required')
        return v
class Run(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    run_id:RunId
class Probe(Run):
    sample:Literal['same-design','other-design']
    human_review_confirmed:Literal[True]
    @field_validator('human_review_confirmed',mode='before')
    @classmethod
    def explicit(cls,v):
        if v is not True:raise ValueError('Human review required')
        return v
class Withdrawal(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    interview_id:RunId
    receipt:SecretStr
    @field_validator('receipt',mode='before')
    @classmethod
    def bounded(cls,v):
        import re
        if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',v):raise ValueError('Invalid receipt')
        return v

def guarded(fn):
    @wraps(fn)
    async def call(*args,**kwargs):
        try:return await fn(*args,**kwargs)
        except VaultError as error:raise HTTPException(409,str(error)) from None
        except OSError:raise HTTPException(503,'Synthetic storage unavailable') from None
    return call

def enabled(interview):
    if not settings.face_workflow_enabled or settings.face_workflow_synthetic_identities.get(interview) not in ('a','c'):
        raise HTTPException(404,'Synthetic face workflow unavailable')

async def online(request,db):
    invitation,interview=await candidate_session(request,db)
    enabled(interview.id);window(interview)
    return binding(interview,invitation)

async def owned(db,user,job_id,interview_id,physical=False):
    enabled(interview_id)
    if physical and interview_id not in settings.face_workflow_viva_interview_ids:raise HTTPException(403,'Viva comparison not authorized')
    interview=await owned_schedule(db,user,job_id,interview_id)
    invitation=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==interview.id).execution_options(populate_existing=True))
    if not invitation or invitation.revoked or not invitation.candidate_session_hash:
        runtime.vault().delete(interview_id);raise HTTPException(409,'Candidate access revoked')
    # Natural invitation expiry is NOT renewed. Recruiter-only viva uses separate authority.
    scope=binding(interview,invitation)
    return scope

def checked(store,scope,run=None):
    row=store.read(scope,run)
    if row['identity']!=settings.face_workflow_synthetic_identities.get(scope.interview_id):raise VaultError('synthetic_identity_changed')
    return row

@router.get('/interview-access/face-workflow')
@guarded
async def candidate_status(request:Request,db=Depends(database_session)):
    scope=await online(request,db);store=runtime.vault()
    try:row=checked(store,scope);state=store.public(row)
    except VaultError as error:
        if str(error) not in ('reference_unavailable','reference_expired','consent_withdrawn'):raise
        state={'state':'withdrawn' if str(error)=='consent_withdrawn' else 'not_enrolled'}
    return {**state,'interview_id':str(scope.interview_id),'wording':WORDING,'version':VERSION,'retention_seconds':store.retention}

@router.post('/interview-access/face-workflow/consent')
@guarded
async def consent(body:Consent,request:Request,db=Depends(database_session)):
    await protect_mutation(request);scope=await online(request,db)
    return runtime.vault().consent(scope,settings.face_workflow_synthetic_identities[scope.interview_id])

@router.post('/interview-access/face-workflow/enroll')
@guarded
async def enroll(body:Run,request:Request,db=Depends(database_session)):
    await protect_mutation(request);scope=await online(request,db);store=runtime.vault();row=checked(store,scope,body.run_id)
    if row['state']!='consented':raise VaultError('reference_already_enrolled')
    result=await runtime.feature(row['identity'],False)
    fresh=await online(request,db)
    if fresh!=scope:raise VaultError('source_changed')
    checked(store,scope,body.run_id)
    return store.enroll(scope,body.run_id,result['feature'],result['provenance'])

@router.post('/interview-access/face-workflow/withdraw')
@guarded
async def candidate_withdraw(body:Run,request:Request,db=Depends(database_session)):
    await protect_mutation(request)
    invitation,interview=await candidate_session(request,db)
    runtime.vault(False).withdraw_authorized(binding(interview,invitation),body.run_id)
    return {'state':'withdrawn'}

@router.post('/face-workflow/withdraw')
@guarded
async def withdraw(body:Withdrawal,request:Request):
    await protect_mutation(request)
    runtime.vault(False).withdraw(body.interview_id,body.receipt.get_secret_value())
    return {'state':'withdrawn'}

@router.get('/jobs/{job_id}/interviews/{interview_id}/face-workflow')
@guarded
async def status(job_id:UUID,interview_id:UUID,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await owned(db,user,job_id,interview_id);store=runtime.vault()
    try:row=checked(store,scope);state=store.public(row)
    except VaultError as error:
        if str(error) not in ('reference_unavailable','reference_expired','consent_withdrawn'):raise
        state={'state':'withdrawn' if str(error)=='consent_withdrawn' else 'not_enrolled'}
    return {**state,'viva_authorized':interview_id in settings.face_workflow_viva_interview_ids,'synthetic_only':True}

@router.post('/jobs/{job_id}/interviews/{interview_id}/face-workflow/verify')
@guarded
async def verify(job_id:UUID,interview_id:UUID,body:Probe,user=Depends(current_recruiter),db=Depends(database_session)):
    scope=await owned(db,user,job_id,interview_id,True);store=runtime.vault();row=checked(store,scope,body.run_id)
    identity=row['identity'] if body.sample=='same-design' else 'c' if row['identity']=='a' else 'a'
    result=await runtime.feature(identity,body.sample=='same-design')
    fresh=await owned(db,user,job_id,interview_id,True)
    if fresh!=scope:raise VaultError('source_changed')
    checked(store,scope,body.run_id)
    return store.compare(scope,body.run_id,result['feature'])

@router.post('/jobs/{job_id}/interviews/{interview_id}/face-workflow/delete')
@guarded
async def delete(job_id:UUID,interview_id:UUID,user=Depends(current_recruiter),db=Depends(database_session)):
    # Owner can delete even if criteria changed, invitation expired or was revoked.
    from app.services.recruiter_records import owned_job
    from app.db.models.recruiter import InterviewSchedule
    await owned_job(db,user.id,job_id,lock=True)
    row=await db.scalar(select(InterviewSchedule).where(InterviewSchedule.id==interview_id,InterviewSchedule.job_id==job_id,InterviewSchedule.recruiter_id==user.id))
    if not row:raise HTTPException(404,'Interview unavailable')
    runtime.vault(False).delete(interview_id);return {'state':'deleted'}
