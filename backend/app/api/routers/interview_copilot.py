"""Authenticated local co-pilot delivery. Deliberately no speech-ingestion route."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.auth import COOKIE_NAME, current_recruiter, database_session, protect_mutation, token_hash
from app.core.config import settings
from app.api.routers.interview_access import candidate_session
from app.db.models.recruiter import InterviewInvitation, InterviewSchedule, JobProfile, Recruiter, RecruiterSession
from app.schemas.batch_screening import ReviewedJobSnapshot
from app.schemas.interview_copilot import Requirement
from app.services.recruiter_records import owned_job
from app.services.livekit_interview import join_window
from app.services.copilot_delivery import Access, DISCLOSURE, VERSION, delivery, Unavailable

router = APIRouter(tags=['Optional interviewer assistant'])


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class Scope(Empty):
    run_id: UUID
    epoch: int = Field(ge=1, strict=True)


class Decision(Scope):
    decision: Literal['accept', 'decline', 'withdraw']
    version: Literal['local-copilot-v1']


class Dismiss(Scope):
    suggestion_id: str = Field(pattern=r'^[a-f0-9]{64}$')


def enabled():
    if not settings.interview_copilot_enabled:
        raise HTTPException(404, 'Interview assistant is disabled.')


@router.get('/interview-copilot/config')
async def configuration():
    return dict(enabled=settings.interview_copilot_enabled, live_connected=False,
        version=VERSION, wording=DISCLOSURE)


async def access(request, db, job_id=None, interview_id=None):
    enabled()
    # Caller authentication is never replaced by a run UUID or a role parameter.
    if job_id is not None:
        user = await current_recruiter(request, db)
        job = await owned_job(db, user.id, job_id, lock=True)
        row = await db.scalar(select(InterviewSchedule).where(InterviewSchedule.id == interview_id,
            InterviewSchedule.job_id == job.id, InterviewSchedule.recruiter_id == user.id)
            .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise HTTPException(404, 'Owned interview not found.')
        recruiter_key = token_hash(request.cookies.get(COOKIE_NAME, ''))
    else:
        invitation, row = await candidate_session(request, db)
        job = await db.scalar(select(JobProfile).where(JobProfile.id == row.job_id)
            .execution_options(populate_existing=True))
        # Candidate auth already holds the job lock. Refresh and lock the child
        # after it, matching the existing invitation parent-lock convention.
        row = await db.scalar(select(InterviewSchedule).where(InterviewSchedule.id == row.id)
            .with_for_update().execution_options(populate_existing=True))
        recruiter_key = delivery.recruiter_key(row.id)
    try:
        join_window(row)
        if job is None or job.confirmed_snapshot is None or job.revision != row.criteria_revision:
            raise ValueError()
        snapshot = ReviewedJobSnapshot.model_validate(job.confirmed_snapshot)
        if snapshot.job_reference != job.job_reference:
            raise ValueError()
        requirements = tuple(Requirement(id=c.criterion_id, description=c.description) for c in snapshot.criteria)
        invitation = await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id == row.id)
            .execution_options(populate_existing=True))
        now = datetime.now(timezone.utc)
        if (invitation is None or invitation.revoked or invitation.expires_at <= now
                or not invitation.candidate_session_hash):
            raise ValueError()
        owner = await db.scalar(select(Recruiter).where(Recruiter.id == row.recruiter_id, Recruiter.active.is_(True)))
        # Check the pinned other participant's authentication on every poll too.
        if owner is None:
            raise ValueError()
        if recruiter_key:
            auth = await db.scalar(select(RecruiterSession).where(RecruiterSession.token_hash == recruiter_key,
                RecruiterSession.recruiter_id == row.recruiter_id, RecruiterSession.expires_at > now))
            if auth is None:
                raise ValueError()
        deadline = min(row.scheduled_at + timedelta(minutes=row.duration_minutes+15), invitation.expires_at).timestamp()
        return Access(row.id, job.id, job.revision, row.recruiter_id, recruiter_key,
            str(invitation.id)+':'+invitation.candidate_session_hash, requirements, deadline,
            row.transcript_storage_revoked_at is not None)
    except (ValueError, TypeError):
        delivery.invalidate(row.id)
        raise HTTPException(409, 'Interview assistant access is unavailable.') from None


def apply(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Unavailable:
        raise HTTPException(409, 'Assistant state changed or is unavailable. Check status before another action.') from None


async def status(request, db, job=None, interview=None, recruiter=False):
    scope = await access(request, db, job, interview)
    return delivery.view(scope, recruiter=recruiter)


@router.get('/jobs/{job}/interviews/{interview}/copilot')
async def recruiter_status(job: UUID, interview: UUID, request: Request, db=Depends(database_session)):
    return await status(request, db, job, interview, True)


@router.get('/interview-access/copilot')
async def candidate_status(request: Request, db=Depends(database_session)):
    return await status(request, db)


@router.post('/jobs/{job}/interviews/{interview}/copilot/prepare')
async def prepare(job: UUID, interview: UUID, request: Request, body: Empty, db=Depends(database_session)):
    await protect_mutation(request)
    scope = await access(request, db, job, interview)
    return apply(delivery.prepare, scope)


async def decide(request, db, body, job=None, interview=None):
    await protect_mutation(request)
    scope = await access(request, db, job, interview)
    return apply(delivery.decide, scope, 'recruiter' if job else 'candidate', body.run_id, body.epoch, body.decision)


@router.post('/jobs/{job}/interviews/{interview}/copilot/consent')
async def recruiter_decide(job: UUID, interview: UUID, request: Request, body: Decision, db=Depends(database_session)):
    return await decide(request, db, body, job, interview)


@router.post('/interview-access/copilot/consent')
async def candidate_decide(request: Request, body: Decision, db=Depends(database_session)):
    return await decide(request, db, body)


@router.post('/jobs/{job}/interviews/{interview}/copilot/dismiss')
async def dismiss(job: UUID, interview: UUID, request: Request, body: Dismiss, db=Depends(database_session)):
    await protect_mutation(request)
    scope = await access(request, db, job, interview)
    return apply(delivery.dismiss, scope, body.run_id, body.epoch, body.suggestion_id)
