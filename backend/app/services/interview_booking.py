"""All booking paths serialize on the owning recruiter row."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.recruiter import Recruiter, InterviewSchedule

async def lock_interviewer(session, owner):
    recruiter = await session.scalar(select(Recruiter).where(Recruiter.id == owner, Recruiter.active.is_(True)).with_for_update())
    if recruiter is None:
        raise HTTPException(404, 'Recruiter unavailable.')

async def check_overlap(session, owner, start, duration):
    end = start + timedelta(minutes=duration)
    rows = (await session.scalars(select(InterviewSchedule).where(
        InterviewSchedule.recruiter_id == owner,
        InterviewSchedule.scheduled_at < end,
        InterviewSchedule.scheduled_at > start - timedelta(minutes=180)))).all()
    if any(r.scheduled_at + timedelta(minutes=r.duration_minutes) > start for r in rows):
        raise HTTPException(409, 'Interview slot is no longer available.')
