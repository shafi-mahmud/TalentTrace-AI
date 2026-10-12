"""Single-use candidate invitations; bearer values never enter URLs or logs here."""
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select

from app.core.auth import current_recruiter, database_session, protect_mutation, token_hash
from app.core.config import settings
from app.db.models.recruiter import InterviewInvitation, InterviewSchedule, JobProfile, Recruiter
from app.services.recruiter_records import owned_job
from app.services.livekit_interview import join_window, livekit_configuration, issue_interview_token, revoke_candidate_access, LiveKitUnavailable
from app.api.routers.interviews import LiveKitTokenRequest, LiveKitTokenResponse

router = APIRouter(tags=["Interview access"])
COOKIE = "talenttrace_interview"
COOKIE_PATH = "/api/v1/interview-access"
_attempts: OrderedDict[str, list[float]] = OrderedDict()


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expires_in_hours: int = Field(default=48, ge=1, le=168, strict=True)


class InvitationResponse(BaseModel):
    token: str = Field(repr=False)
    expires_at: datetime


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: SecretStr

    @field_validator("token", mode="before")
    @classmethod
    def bounded_token(cls, value):
        import re
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise ValueError("Invalid invitation.")
        return value


def throttle(request):
    key = token_hash(request.client.host if request.client else "unknown")
    now = time.monotonic()
    recent = [t for t in _attempts.pop(key, []) if now - t < 60]
    if len(_attempts) >= 1000:
        _attempts.popitem(last=False)
    if len(recent) >= 20:
        _attempts[key] = recent
        raise HTTPException(429, "Too many interview access attempts. Wait one minute.")
    _attempts[key] = recent + [now]


async def owned_schedule(session, user, job_id, interview_id):
    job = await owned_job(session, user.id, job_id, lock=True)
    row = await session.scalar(select(InterviewSchedule).where(InterviewSchedule.id == interview_id,
        InterviewSchedule.job_id == job.id, InterviewSchedule.recruiter_id == user.id))
    if row is None:
        raise HTTPException(404, "Owned scheduled interview not found.")
    if job.confirmed_snapshot is None or job.revision != row.criteria_revision:
        raise HTTPException(409, "Review current interview criteria first.")
    return row


async def remove_claimed(row):
    if row.candidate_session_hash:
        try:
            await revoke_candidate_access(row.interview_id, row.id)
        except Exception:
            raise HTTPException(502, "Invitation is revoked, but live disconnection was not confirmed. Retry revocation before sharing a replacement.") from None


@router.post("/jobs/{job_id}/interviews/{interview_id}/invitation", response_model=InvitationResponse)
async def create_invitation(job_id: UUID, interview_id: UUID, body: InvitationRequest,
    user=Depends(current_recruiter), session=Depends(database_session)):
    interview = await owned_schedule(session, user, job_id, interview_id)
    try:
        livekit_configuration()
    except LiveKitUnavailable:
        raise HTTPException(503, "LiveKit synthetic interview testing is not configured.") from None
    now = datetime.now(timezone.utc)
    expires = min(now + timedelta(hours=body.expires_in_hours),
        interview.scheduled_at + timedelta(minutes=interview.duration_minutes + 15))
    if expires <= now:
        raise HTTPException(409, "Interview has ended.")
    row = await session.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id == interview.id))
    if row:
        previous_id = row.id
        row.revoked = True
        await session.commit()
        await remove_claimed(row)
        # Reacquire the parent lock after revocation's commit and network call.
        await owned_schedule(session, user, job_id, interview_id)
        row = await session.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id == interview.id)
            .execution_options(populate_existing=True))
        if row.id != previous_id or not row.revoked:
            raise HTTPException(409, "Invitation changed. Review current access before generating another.")
    else:
        row = InterviewInvitation(interview_id=interview.id)
        session.add(row)
    raw = secrets.token_urlsafe(32)
    row.id = uuid4()
    row.token_hash = token_hash(raw)
    row.candidate_session_hash = None
    row.expires_at = expires
    row.revoked = False
    await session.commit()
    return InvitationResponse(token=raw, expires_at=expires)


@router.post("/jobs/{job_id}/interviews/{interview_id}/invitation/revoke")
async def revoke_invitation(job_id: UUID, interview_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    # Revocation remains available even if job criteria have since changed.
    await owned_job(session, user.id, job_id, lock=True)
    interview = await session.scalar(select(InterviewSchedule).where(InterviewSchedule.id == interview_id,
        InterviewSchedule.job_id == job_id, InterviewSchedule.recruiter_id == user.id))
    if interview is None:
        raise HTTPException(404, "Owned scheduled interview not found.")
    row = await session.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id == interview.id))
    if row:
        row.revoked = True
        await session.commit()
        await remove_claimed(row)
    return {"status": "revoked"}


async def candidate_records(session, digest, claiming=False):
    field = InterviewInvitation.token_hash if claiming else InterviewInvitation.candidate_session_hash
    initial = await session.scalar(select(InterviewInvitation).where(field == digest))
    if initial is None:
        raise HTTPException(401, "Interview access is unavailable.")
    interview = await session.scalar(select(InterviewSchedule).where(InterviewSchedule.id == initial.interview_id))
    if interview is None:
        raise HTTPException(401, "Interview access is unavailable.")
    # Same parent lock order as recruiter mutations serializes claim/revoke/rotation.
    job = await session.scalar(select(JobProfile).where(JobProfile.id == interview.job_id).with_for_update())
    # The initial lookup may already be cached before waiting on the parent lock.
    # Refresh it so a concurrent claim/revocation cannot reuse stale ORM values.
    row = await session.scalar(select(InterviewInvitation).where(field == digest)
        .execution_options(populate_existing=True))
    owner = await session.scalar(select(Recruiter).where(Recruiter.id == interview.recruiter_id, Recruiter.active.is_(True)))
    if (row is None or row.revoked or row.expires_at <= datetime.now(timezone.utc) or owner is None
        or job is None or job.recruiter_id != interview.recruiter_id
        or job.confirmed_snapshot is None or job.revision != interview.criteria_revision):
        raise HTTPException(401, "Interview access is unavailable.")
    return row, interview


@router.post("/interview-access/exchange", dependencies=[Depends(protect_mutation)])
async def exchange(body: ExchangeRequest, request: Request, response: Response, session=Depends(database_session)):
    throttle(request)
    row, _ = await candidate_records(session, token_hash(body.token.get_secret_value()), claiming=True)
    if row.candidate_session_hash is not None:
        raise HTTPException(409, "Invitation has already been used. Reconnect in the original browser or request a replacement.")
    raw = secrets.token_urlsafe(32)
    row.candidate_session_hash = token_hash(raw)
    await session.commit()
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.environment != "development",
        samesite="strict", path=COOKIE_PATH, max_age=max(1, int((row.expires_at-datetime.now(timezone.utc)).total_seconds())))
    return {"status": "ready"}


async def candidate_session(request, session):
    raw = request.cookies.get(COOKIE, "")
    if len(raw) != 43:
        raise HTTPException(401, "Interview access is unavailable.")
    return await candidate_records(session, token_hash(raw))


@router.get("/interview-access/status")
async def candidate_status(request: Request, session=Depends(database_session)):
    _, interview = await candidate_session(request, session)
    try:
        join_window(interview)
    except ValueError:
        raise HTTPException(409, "Interview join window is closed.") from None
    return {"status": "ready"}


@router.post("/interview-access/livekit-token", response_model=LiveKitTokenResponse, dependencies=[Depends(protect_mutation)])
async def candidate_token(body: LiveKitTokenRequest, request: Request, session=Depends(database_session)):
    throttle(request)
    row, interview = await candidate_session(request, session)
    try:
        ttl = min(join_window(interview), max(1, int((row.expires_at-datetime.now(timezone.utc)).total_seconds())))
    except ValueError:
        raise HTTPException(409, "Interview join window is closed.") from None
    try:
        return LiveKitTokenResponse(**issue_interview_token(interview.id, row.id, "candidate", ttl))
    except LiveKitUnavailable:
        raise HTTPException(503, "LiveKit synthetic interview testing is not configured.") from None
    except Exception:
        raise HTTPException(502, "Interview access could not be issued.") from None
