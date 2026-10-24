"""Explicit reviewed send with a committed interview-scoped reservation."""
import hmac
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.auth import current_recruiter, database_session
from app.core.config import settings
from app.db.models.recruiter import BookedInterviewEmailAttempt, SchedulingInvitation
from app.api.routers.interview_access import owned_schedule
from app.services.recruiter_records import owned_job
from app.services.interview_booking import lock_interviewer
from app.services.interview_email import recipient
from app.services import booked_interview_email as delivery

router = APIRouter(tags=['Booked appointment email'])


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    recipient: str = Field(min_length=3, max_length=254, repr=False)


class SendRequest(ReviewRequest):
    review_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: Literal[True]

    @field_validator('confirmed', mode='before')
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError('Explicit confirmation required.')
        return value


def status(attempt):
    return 'uncertain' if attempt.status == 'sending' else attempt.status


async def context(session, user, job_id, interview_id):
    row = await owned_schedule(session, user, job_id, interview_id)
    # Candidate-selected bookings retain their separate confirmation semantics.
    if await session.scalar(select(SchedulingInvitation).where(SchedulingInvitation.interview_id == row.id)):
        raise HTTPException(409, 'Use the existing candidate self-scheduling confirmation flow.')
    job = await owned_job(session, user.id, job_id)
    return job, row


async def attempt_for(session, row):
    return await session.scalar(select(BookedInterviewEmailAttempt).where(BookedInterviewEmailAttempt.interview_id == row.id))


@router.get('/jobs/{job_id}/interviews/{interview_id}/appointment-email')
async def get_status(job_id: UUID, interview_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    _, row = await context(session, user, job_id, interview_id)
    attempt = await attempt_for(session, row)
    return {'email_status': status(attempt) if attempt else ('none' if delivery.ready(settings) else 'not_configured')}


@router.post('/jobs/{job_id}/interviews/{interview_id}/appointment-email/preview')
async def review_email(job_id: UUID, interview_id: UUID, body: ReviewRequest,
        user=Depends(current_recruiter), session=Depends(database_session)):
    job, row = await context(session, user, job_id, interview_id)
    to = recipient(settings, body.recipient)
    if not delivery.ready(settings):
        raise HTTPException(503, 'Appointment email is not configured.')
    if row.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(409, 'Only upcoming appointments can be confirmed.')
    if await attempt_for(session, row):
        raise HTTPException(409, 'A delivery attempt already exists. Reload its status; do not resend.')
    return delivery.preview(job, row, to)


@router.post('/jobs/{job_id}/interviews/{interview_id}/appointment-email')
async def send_email(job_id: UUID, interview_id: UUID, body: SendRequest,
        user=Depends(current_recruiter), session=Depends(database_session)):
    return await send_reviewed(job_id, interview_id, body, user, session)


async def send_reviewed(job_id, interview_id, body, user, session, *, configuration=None, transport=None):
    c = configuration or settings
    await lock_interviewer(session, user.id)
    job, row = await context(session, user, job_id, interview_id)
    previous = await attempt_for(session, row)
    if previous:
        return {'email_status': status(previous)}
    to = recipient(c, body.recipient)
    if not delivery.ready(c):
        raise HTTPException(503, 'Appointment email is not configured.')
    if row.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(409, 'Only upcoming appointments can be confirmed.')
    reviewed = delivery.preview(job, row, to)
    if not hmac.compare_digest(reviewed['review_digest'], body.review_digest):
        raise HTTPException(409, 'Saved appointment or recipient changed. Review again.')
    attempt = BookedInterviewEmailAttempt(interview_id=row.id, status='sending')
    session.add(attempt)
    try:
        await session.commit()  # Durable reservation BEFORE any SMTP I/O.
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, 'A delivery attempt exists. Reload status; do not resend.') from None
    outcome = await delivery.dispatch(c, to, reviewed['subject'], reviewed['body'], transport)
    attempt.status = outcome
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        return {'email_status': 'uncertain'}
    return {'email_status': outcome}
