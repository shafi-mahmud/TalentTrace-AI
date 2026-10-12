"""Explicit human selection from saved eligibility; no external side effects."""
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.auth import current_recruiter, database_session
from app.db.models.recruiter import InterviewSchedule
from app.schemas.interview import InterviewRequest, InterviewResponse
from app.services.recruiter_records import owned_job
from app.services.score_records import load_scores
from app.services.livekit_interview import issue_interview_token, LiveKitUnavailable

router = APIRouter(tags=["Interview scheduling"])


class LiveKitTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    slot: Literal["a", "b"]
    synthetic_test_confirmed: Literal[True]

    @field_validator("synthetic_test_confirmed", mode="before")
    @classmethod
    def explicit_synthetic(cls, value):
        if value is not True:
            raise ValueError("Explicit synthetic testing confirmation is required.")
        return value


class LiveKitTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    server_url: str
    token: str = Field(repr=False, min_length=32, max_length=8192)
    expires_in: Literal[300]


@router.post("/jobs/{job_id}/interviews/{interview_id}/livekit-token", response_model=LiveKitTokenResponse)
async def livekit_token(job_id: UUID, interview_id: UUID, body: LiveKitTokenRequest,
    user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id, lock=True)
    row = await session.scalar(select(InterviewSchedule).where(InterviewSchedule.id == interview_id,
        InterviewSchedule.job_id == job.id, InterviewSchedule.recruiter_id == user.id))
    if row is None:
        raise HTTPException(404, "Owned scheduled interview not found.")
    if job.confirmed_snapshot is None or row.criteria_revision != job.revision:
        raise HTTPException(409, "Review the scheduled interview against the current approved job criteria first.")
    try:
        return LiveKitTokenResponse(**issue_interview_token(row.id, user.id, body.slot))
    except LiveKitUnavailable:
        raise HTTPException(503, "LiveKit synthetic interview testing is not configured.") from None
    except Exception:
        raise HTTPException(502, "Interview access could not be issued.") from None


def public_interview(row, job):
    try:
        return InterviewResponse(**{key: getattr(row, key) for key in InterviewResponse.model_fields
            if key not in {"job_reference", "status"}}, job_reference=job.job_reference)
    except (ValueError, TypeError):
        raise HTTPException(500, "Saved interview could not be validated.") from None


@router.post("/jobs/{job_id}/interviews", response_model=InterviewResponse, status_code=201)
async def schedule_interview(job_id: UUID, body: InterviewRequest,
    user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id, lock=True)
    if body.criteria_revision != job.revision:
        raise HTTPException(409, "Job changed. Review the current screening results before scheduling.")
    if body.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Interview start must be in the future.")
    saved = await load_scores(session, job, body.batch_id)
    candidate = next((c for c in saved.candidates if c.upload_id == body.upload_id), None)
    if candidate is None:
        raise HTTPException(404, "Saved candidate evaluation not found.")
    if candidate.screening_decision != "eligible" or (candidate.status != "scored" and candidate.reason not in
        {"uncertain_evidence", "missing_dimension_criteria"}):
        raise HTTPException(409, "Only completed eligible screening records can be selected.")
    unscored = candidate.status != "scored"
    if unscored and not body.confirm_eligible_unscored:
        raise HTTPException(409, "Eligible candidate has no score. Review the uncertainty and explicitly confirm selection.")
    existing = await session.scalar(select(InterviewSchedule).where(InterviewSchedule.job_id == job.id,
        InterviewSchedule.batch_id == body.batch_id, InterviewSchedule.upload_id == body.upload_id))
    if existing is not None:
        raise HTTPException(409, "An initial interview is already scheduled for this candidate.")
    row = InterviewSchedule(recruiter_id=user.id, job_id=job.id, batch_id=body.batch_id, upload_id=body.upload_id,
        criteria_revision=job.revision, scoring_version=saved.scoring_version, scheduled_at=body.scheduled_at,
        timezone=body.timezone, duration_minutes=body.duration_minutes, unscored_confirmed=unscored,
        screening_snapshot=candidate.model_dump(mode="json"))
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Interview could not be saved. Reload saved interviews before another attempt.") from None
    return public_interview(row, job)


@router.get("/jobs/{job_id}/interviews", response_model=list[InterviewResponse])
async def list_interviews(job_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id)
    rows = (await session.scalars(select(InterviewSchedule).where(InterviewSchedule.job_id == job.id,
        InterviewSchedule.recruiter_id == user.id).order_by(InterviewSchedule.scheduled_at, InterviewSchedule.id).limit(100))).all()
    return [public_interview(row, job) for row in rows]
