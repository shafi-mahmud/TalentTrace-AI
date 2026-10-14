"""Explicit allowlisted recruiter send. No resend after a recorded attempt."""
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select
from datetime import datetime,timezone
from app.core.auth import current_recruiter,database_session,token_hash
from app.core.config import settings
from app.db.models.recruiter import SchedulingInvitation,InterviewEmailAttempt
from app.services.interview_booking import lock_interviewer
from app.services.interview_email import ready,recipient,finish_attempt
from app.api.routers.self_scheduling import Selection,selected,create_scheduling_invitation
router=APIRouter(tags=['Synthetic interview email'])
class EmailSelection(Selection):
 recipient:str=Field(min_length=3,max_length=254,repr=False)
@router.post('/jobs/{job_id}/scheduling-invitations/email')
async def send_scheduling_email(job_id:UUID,body:EmailSelection,user=Depends(current_recruiter),session=Depends(database_session)):
 return await send_selected_email(job_id,body,user,session)

async def send_selected_email(job_id,body,user,session,*,configuration=None,on_reserved=None):
 c=configuration or settings
 await lock_interviewer(session,user.id)
 await selected(session,user.id,job_id,body)
 to=recipient(c,body.recipient)
 if not ready(c):raise HTTPException(503,'Interview email is disabled or not configured.')
 # Under the same recruiter lock as invitation rotation/booking. Recorded outcomes
 # are never resent, including interrupted/uncertain sending state.
 previous=(await session.scalars(select(SchedulingInvitation).where(SchedulingInvitation.job_id==job_id,SchedulingInvitation.batch_id==body.batch_id,SchedulingInvitation.upload_id==body.upload_id,SchedulingInvitation.criteria_revision==body.criteria_revision,SchedulingInvitation.revoked.is_(False)).order_by(SchedulingInvitation.expires_at.desc()).limit(1))).first()
 if previous:
  if previous.expires_at<=datetime.now(timezone.utc) or previous.interview_id:raise HTTPException(409,'Invitation expired or already booked. Review saved outcome.')
  attempt=await session.scalar(select(InterviewEmailAttempt).where(InterviewEmailAttempt.scheduling_invitation_id==previous.id,InterviewEmailAttempt.kind=='scheduling'))
  if attempt:
   if previous.recipient_email!=to:raise HTTPException(409,'Recipient differs from existing invitation. Review before replacement.')
   return {'email_status':'uncertain' if attempt.status=='sending' else attempt.status,'reused':True}
 value=await create_scheduling_invitation(job_id,body,user,session,commit=False)
 invitation=await session.scalar(select(SchedulingInvitation).where(SchedulingInvitation.token_hash==token_hash(value['token'])))
 invitation.recipient_email=to
 attempt=InterviewEmailAttempt(id=uuid4(),scheduling_invitation_id=invitation.id,kind='scheduling',status='sending');session.add(attempt)
 if on_reserved:on_reserved(attempt)
 await session.commit() # Durable reservation precedes SMTP; no transaction spans network I/O.
 status=await finish_attempt(session,attempt,c,to,'scheduling',value['token'])
 return {'email_status':status,'reused':False}
