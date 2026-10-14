"""Explicit recruiter selection followed by bounded bearer-authorized booking."""
import secrets
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,SecretStr,AwareDatetime
from sqlalchemy import select
from app.core.auth import current_recruiter,database_session,protect_mutation,token_hash
from app.db.models.recruiter import SchedulingInvitation,InterviewInvitation,InterviewSchedule
from app.services.recruiter_records import owned_job
from app.services.score_records import load_scores
from app.services.interview_booking import lock_interviewer,check_overlap
from app.services.interview_slots import offered_slots
from app.api.routers.interviews import create_selected_interview
from app.api.routers.interview_access import throttle
from app.schemas.interview import InterviewRequest
router=APIRouter(tags=['Synthetic candidate scheduling'])
class Selection(BaseModel):
 model_config=ConfigDict(extra='forbid')
 batch_id:UUID
 upload_id:UUID
 criteria_revision:int=Field(ge=1,strict=True)
 selection_confirmed:bool=Field(strict=True)
 confirm_eligible_unscored:bool=Field(default=False,strict=True)
class Capability(BaseModel):
 model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
 token:SecretStr=Field(min_length=43,max_length=43)
class Booking(Capability):
 scheduled_at:AwareDatetime
async def selected(session,owner,job_id,body):
 job=await owned_job(session,owner,job_id,lock=True)
 if not body.selection_confirmed or job.revision!=body.criteria_revision:raise HTTPException(409,'Review current selection.')
 saved=await load_scores(session,job,body.batch_id)
 c=next((x for x in saved.candidates if x.upload_id==body.upload_id),None)
 if not c or c.screening_decision!='eligible' or (c.status!='scored' and (c.reason not in {'uncertain_evidence','missing_dimension_criteria'} or not body.confirm_eligible_unscored)):
  raise HTTPException(409,'Current eligible candidate and explicit approval required.')
 return job
@router.post('/jobs/{job_id}/scheduling-invitations')
async def invite(job_id:UUID,body:Selection,user=Depends(current_recruiter),session=Depends(database_session)):
 return await create_scheduling_invitation(job_id,body,user,session)
async def create_scheduling_invitation(job_id,body,user,session,*,commit=True):
 await lock_interviewer(session,user.id);await selected(session,user.id,job_id,body)
 exists=await session.scalar(select(InterviewSchedule.id).where(InterviewSchedule.job_id==job_id,InterviewSchedule.batch_id==body.batch_id,InterviewSchedule.upload_id==body.upload_id))
 if exists:raise HTTPException(409,'Candidate already scheduled.')
 old=(await session.scalars(select(SchedulingInvitation).where(SchedulingInvitation.job_id==job_id,SchedulingInvitation.batch_id==body.batch_id,SchedulingInvitation.upload_id==body.upload_id,SchedulingInvitation.revoked.is_(False)))).all()
 for row in old:row.revoked=True
 raw=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(days=7)
 session.add(SchedulingInvitation(recruiter_id=user.id,job_id=job_id,batch_id=body.batch_id,upload_id=body.upload_id,criteria_revision=body.criteria_revision,token_hash=token_hash(raw),expires_at=expires,unscored_confirmed=body.confirm_eligible_unscored,revoked=False))
 if commit:await session.commit()
 else:await session.flush()
 return {'token':raw,'expires_at':expires}
async def capability(session,body,request):
 throttle(request)
 row=await session.scalar(select(SchedulingInvitation).where(SchedulingInvitation.token_hash==token_hash(body.token.get_secret_value())))
 if row is None:raise HTTPException(401,'Scheduling invitation unavailable.')
 await lock_interviewer(session,row.recruiter_id)
 await session.refresh(row)
 if row.revoked or row.expires_at<=datetime.now(timezone.utc):raise HTTPException(401,'Scheduling invitation unavailable.')
 if row.interview_id:raise HTTPException(409,'Invitation already booked. Contact recruiter for joining access.')
 selection=Selection(batch_id=row.batch_id,upload_id=row.upload_id,criteria_revision=row.criteria_revision,selection_confirmed=True,confirm_eligible_unscored=row.unscored_confirmed)
 await selected(session,row.recruiter_id,row.job_id,selection)
 return row
@router.post('/interview-scheduling/slots',dependencies=[Depends(protect_mutation)])
async def slots(body:Capability,request:Request,session=Depends(database_session)):
 row=await capability(session,body,request);available=[]
 for slot in offered_slots():
  try:await check_overlap(session,row.recruiter_id,slot,60)
  except HTTPException as e:
   if e.status_code==409:continue
   raise
  available.append(slot)
 return {'timezone':'Asia/Dhaka','duration_minutes':60,'slots':available}
@router.post('/interview-scheduling/book',status_code=201,dependencies=[Depends(protect_mutation)])
async def book(body:Booking,request:Request,session=Depends(database_session)):
 row=await capability(session,body,request);start=body.scheduled_at.astimezone(timezone.utc)
 if start not in offered_slots():raise HTTPException(422,'Choose a currently offered demo slot.')
 selection=InterviewRequest(batch_id=row.batch_id,upload_id=row.upload_id,criteria_revision=row.criteria_revision,selection_confirmed=True,confirm_eligible_unscored=row.unscored_confirmed,scheduled_at=start,timezone='Asia/Dhaka',duration_minutes=60)
 result=await create_selected_interview(row.job_id,selection,SimpleNamespace(id=row.recruiter_id),session,commit=False)
 row.interview_id=result.id
 raw=secrets.token_urlsafe(32);expires=start+timedelta(minutes=75)
 session.add(InterviewInvitation(interview_id=result.id,token_hash=token_hash(raw),expires_at=expires,revoked=False))
 email_status='not_requested';attempt=None
 if row.recipient_email:
  from app.db.models.recruiter import InterviewEmailAttempt
  attempt=InterviewEmailAttempt(scheduling_invitation_id=row.id,kind='confirmation',status='sending')
  session.add(attempt)
 await session.commit()
 if attempt:
  from app.services.interview_email import finish_attempt
  from app.core.config import settings
  email_status=await finish_attempt(session,attempt,settings,row.recipient_email,'confirmation',raw,result)
 return {'interview':result,'joining_token':raw,'expires_at':expires,'email_status':email_status}
