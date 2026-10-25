"""Opt-in coarse browser status. Process-local, short-lived; no activity history."""
import asyncio
import time
from uuid import UUID,uuid4
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException
from pydantic import BaseModel,ConfigDict
from sqlalchemy import select
from app.core.auth import current_recruiter,database_session,protect_mutation
from app.api.routers.interview_access import candidate_session,owned_schedule
from app.services.livekit_interview import join_window
from app.db.models.recruiter import InterviewInvitation

router=APIRouter(tags=['Optional interview activity'])
class Empty(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
class Consent(Empty):
    version:Literal["attention-v1"]
    decision:Literal["accept"]
class Scope(Empty):run_id:UUID
class Signal(Scope):
    visibility:Literal['visible','hidden','unsupported']
    fullscreen:Literal['active','inactive','unsupported']

class ActivityStore:
    def __init__(self,clock=time.monotonic):self.records={};self.clock=clock
    def remove(self,interview):
        row=self.records.pop(interview,None)
        if row and row.get('timer'):row['timer'].cancel()
    def checked(self,interview,identity):
        row=self.records.get(interview)
        if row and (row['identity']!=identity or row['expires']<=self.clock()):self.remove(interview);row=None
        return row
    def renew(self,interview,row):
        if row.get('timer'):row['timer'].cancel()
        row['expires']=self.clock()+30
        def expire():
            if self.records.get(interview) is row:self.remove(interview)
        row['timer']=asyncio.get_running_loop().call_later(30,expire)
    def start(self,interview,identity):
        if self.checked(interview,identity):raise HTTPException(409,'Status sharing already active.')
        for key,row in list(self.records.items()):
            if row['expires']<=self.clock():self.remove(key)
        if len(self.records)>=64:raise HTTPException(503,'Status sharing unavailable.')
        row=dict(identity=identity,run_id=uuid4(),visibility='unsupported',fullscreen='unsupported')
        self.records[interview]=row;self.renew(interview,row);return row['run_id']
    def update(self,interview,identity,signal):
        row=self.checked(interview,identity)
        if not row or row['run_id']!=signal.run_id:raise HTTPException(409,'Status sharing is unavailable.')
        row.update(visibility=signal.visibility,fullscreen=signal.fullscreen);self.renew(interview,row)
    def withdraw(self,interview,identity,run):
        row=self.checked(interview,identity)
        if row and row['run_id']==run:self.remove(interview)
    def view(self,interview,identity):
        row=self.checked(interview,identity)
        return {'state':'not_shared'} if not row else dict(state='shared',visibility=row['visibility'],fullscreen=row['fullscreen'])
store=ActivityStore()

def window(interview):
    try:join_window(interview)
    except ValueError:raise HTTPException(409,'Interview unavailable.') from None
async def candidate(request,db):
    row,interview=await candidate_session(request,db);window(interview)
    return interview.id,(row.id,row.candidate_session_hash)

@router.post('/interview-access/attention/consent')
async def consent(request:Request,body:Consent,db=Depends(database_session)):
    await protect_mutation(request);interview,identity=await candidate(request,db)
    return {'run_id':str(store.start(interview,identity))}
@router.post('/interview-access/attention')
async def report(request:Request,body:Signal,db=Depends(database_session)):
    await protect_mutation(request);interview,identity=await candidate(request,db)
    store.update(interview,identity,body);return {'status':'accepted'}
@router.post('/interview-access/attention/withdraw')
async def withdraw(request:Request,body:Scope,db=Depends(database_session)):
    await protect_mutation(request);interview,identity=await candidate(request,db)
    store.withdraw(interview,identity,body.run_id);return {'status':'withdrawn'}
@router.get('/jobs/{job_id}/interviews/{interview_id}/attention')
async def status(job_id:UUID,interview_id:UUID,request:Request,user=Depends(current_recruiter),db=Depends(database_session)):
    interview=await owned_schedule(db,user,job_id,interview_id);window(interview)
    row=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==interview.id).execution_options(populate_existing=True))
    if not row or row.revoked or not row.candidate_session_hash or row.expires_at<=datetime.now(timezone.utc):
        store.remove(interview.id);return {'state':'not_shared'}
    return store.view(interview.id,(row.id,row.candidate_session_hash))
