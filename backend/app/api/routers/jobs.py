"""One owner-scoped job context shared by chat and screening; no automatic approval."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.core.auth import current_recruiter, database_session
from app.db.models.recruiter import ChatTurn, JobProfile, RecruiterConversation
from app.schemas.batch_screening import ReviewedJobSnapshot, ScreeningSuggestions
from app.schemas.job_description import JobTitle
from app.schemas.recruiter_chat import RecruiterChatResponse
from app.schemas.screening import ScreeningCriterion
from app.schemas.candidate_score import ScoringWeights
from app.services.score_records import load_scores, ScoringBatch
from app.services.recruiter_records import job_view, owned_job
from pydantic import TypeAdapter, ValidationError

router = APIRouter(tags=["Owned jobs and conversations"])


class ManualJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    job_title: JobTitle

    @field_validator("job_title")
    @classmethod
    def safe_title(cls, value):
        return ReviewedJobSnapshot.safe_title(value)


class CriteriaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    revision: int = Field(ge=1)
    criteria: list[ScreeningCriterion] = Field(min_length=1, max_length=50)
    confirmed: bool
    weights: ScoringWeights = Field(default_factory=ScoringWeights)

    @field_validator("criteria")
    @classmethod
    def unique_ids(cls, value):
        ids = [item.criterion_id.casefold() for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion identifiers must be unique.")
        return value


@router.get("/jobs")
async def list_jobs(user=Depends(current_recruiter), session=Depends(database_session)):
    jobs = (await session.scalars(select(JobProfile).where(JobProfile.recruiter_id == user.id).order_by(JobProfile.id).limit(100))).all()
    return [job_view(job) for job in jobs]


@router.post("/jobs", status_code=201)
async def create_job(body: ManualJobRequest, user=Depends(current_recruiter), session=Depends(database_session)):
    identity = uuid4()
    job = JobProfile(id=identity, recruiter_id=user.id, job_reference="TT-JOB-"+identity.hex[:16].upper(),
        job_title=body.job_title, suggestions=ScreeningSuggestions(job_title=body.job_title, criteria=[]).model_dump(mode="json"),
        sources=[], revision=1)
    session.add(job)
    await session.commit()
    return job_view(job)


@router.put("/jobs/{job_id}/criteria")
async def update_criteria(job_id: UUID, body: CriteriaUpdate, user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id, lock=True)
    if job.revision != body.revision:
        raise HTTPException(409, "Job changed. Reload and review the latest requirements.")
    snapshot = ReviewedJobSnapshot(job_reference=job.job_reference, job_title=job.job_title,
                                   criteria_confirmed=True, criteria=body.criteria)
    job.suggestions = ScreeningSuggestions(job_title=job.job_title, criteria=body.criteria).model_dump(mode="json")
    ids = {item.criterion_id for item in body.criteria}
    job.sources = [source for source in job.sources if source["criterion_id"] in ids]
    job.confirmed_snapshot = snapshot.model_dump(mode="json") if body.confirmed else None
    job.scoring_weights = body.weights.model_dump()
    job.revision += 1
    await session.commit()
    return job_view(job)


@router.get("/conversations")
async def conversations(user=Depends(current_recruiter), session=Depends(database_session)):
    rows = (await session.scalars(select(RecruiterConversation).where(RecruiterConversation.recruiter_id == user.id)
                                 .order_by(RecruiterConversation.expires_at.desc()).limit(100))).all()
    return [{"id": str(row.id), "expires_at": row.expires_at.isoformat()} for row in rows]


@router.get("/jobs/{job_id}/batches/{batch_id}/scores", response_model=ScoringBatch)
async def saved_scores(job_id: UUID, batch_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id, lock=True)
    return await load_scores(session, job, batch_id)


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    row = await session.scalar(select(RecruiterConversation).where(RecruiterConversation.id == conversation_id,
                                                                 RecruiterConversation.recruiter_id == user.id))
    if row is None:
        raise HTTPException(404, "Conversation not found.")
    turns = (await session.scalars(select(ChatTurn).where(ChatTurn.conversation_id == row.id).order_by(ChatTurn.sequence).limit(20))).all()
    adapter = TypeAdapter(RecruiterChatResponse)
    try:
        from app.integrations.llm.selection import MODELS
        provider = row.state.get('ai_provider', 'groq')
        if provider not in {'groq', *('ollama:'+model for model in MODELS)}:
            raise ValueError('Invalid stored provider.')
        return {"id": str(row.id), "ai_provider": provider, "turns": [{"message": turn.recruiter_message,
            "reply": adapter.validate_python(turn.response).model_dump(mode="json", exclude_none=True)} for turn in turns]}
    except (ValidationError, ValueError):
        raise HTTPException(500, "Saved conversation could not be validated.") from None

@router.get('/jobs/{job_id}/scores', response_model=list[ScoringBatch])
async def saved_job_scores(job_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    """Bounded current-revision discovery; never invokes parsing or screening."""
    from app.db.models.recruiter import CandidateScoreRecord
    from app.services.score_records import SCORING_VERSION
    job = await owned_job(session, user.id, job_id)
    if job.confirmed_snapshot is None:
        raise HTTPException(409, 'Review and confirm current criteria first.')
    revision, snapshot = job.revision, job.confirmed_snapshot
    batches = (await session.scalars(select(CandidateScoreRecord.batch_id).where(
        CandidateScoreRecord.job_id == job.id,
        CandidateScoreRecord.criteria_revision == revision,
        CandidateScoreRecord.scoring_version == SCORING_VERSION).distinct().order_by(
        CandidateScoreRecord.batch_id).limit(21))).all()
    if len(batches) > 20:
        raise HTTPException(409, 'Saved batch listing limit exceeded.')
    results = [await load_scores(session, job, batch_id) for batch_id in batches]
    await session.refresh(job)
    if job.revision != revision or job.confirmed_snapshot != snapshot:
        raise HTTPException(409, 'Job changed. Reload current criteria.')
    return results
