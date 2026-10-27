"""Owned, revision-bound score persistence; no browser-supplied evidence/results."""
from uuid import UUID
from copy import deepcopy
from typing import Literal, Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator, StringConstraints
from sqlalchemy import select, delete

from app.db.models.recruiter import CandidateScoreRecord
from app.schemas.candidate_score import CandidateScore, ScoringWeights
from app.schemas.cv_upload import JobReference
from app.services.candidate_scoring import score_candidate

SCORING_VERSION = "f2-coverage-v1"


def restore_candidate_score(payload):
    # JSONB arrays must be explicitly restored for the existing strict tuple
    # evidence contract; do not weaken screening models or use a generic decoder.
    value = deepcopy(payload)
    value.pop("_ai_provenance", None)  # Execution metadata is separate from validated scoring evidence.
    for dimension in value.get("dimensions", []):
        for match in dimension.get("matches", []):
            if isinstance(match.get("evidence"), list):
                match["evidence"] = tuple(match["evidence"])
    return CandidateScore.model_validate(value)


class ScoreRank(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    upload_id: UUID
    score: float = Field(ge=0, le=100)
    rank: int = Field(ge=1, le=20)
    tied: bool


def score_ranking(candidates):
    rows = sorted((c for c in candidates if c.status == "scored"), key=lambda c: (-c.score, c.upload_id.hex))
    return [ScoreRank(upload_id=c.upload_id, score=c.score,
        rank=1 + sum(other.score > c.score for other in rows),
        tied=sum(other.score == c.score for other in rows) > 1) for c in rows]


class AIProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    provider: Literal['groq', 'ollama']
    model: Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]*$')]
    external_processing_confirmed: bool

    @model_validator(mode='after')
    def consistent(self):
        if '://' in self.model or self.external_processing_confirmed != (self.provider == 'groq'):
            raise ValueError('Invalid stored AI provenance.')
        return self


class ScoringBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: UUID
    job_reference: JobReference
    batch_id: UUID
    criteria_revision: int = Field(ge=1)
    scoring_version: str = SCORING_VERSION
    weights: ScoringWeights
    candidates: tuple[CandidateScore, ...] = Field(min_length=1, max_length=20)
    ranking: tuple[ScoreRank, ...] = Field(max_length=20)
    ai_provenance: AIProvenance | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.scoring_version != SCORING_VERSION or len({c.upload_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Scoring identity/version is invalid.")
        if any(c.job_reference != self.job_reference or c.weights != self.weights for c in self.candidates):
            raise ValueError("Scores must share one job and approved weights.")
        if self.ranking != tuple(score_ranking(self.candidates)):
            raise ValueError("Score ranking must contain only scored eligible candidates.")
        return self


async def persist_scores(session, job, batch, *, ai_provenance=None):
    provenance = AIProvenance.model_validate(ai_provenance) if ai_provenance is not None else None
    weights = ScoringWeights.model_validate(job.scoring_weights or {})
    candidates = tuple(score_candidate(item.result, job_reference=job.job_reference, criteria=batch.snapshot.criteria, weights=weights)
        if item.result else CandidateScore(job_reference=job.job_reference, upload_id=item.upload_id,
            screening_decision=None, status="not_evaluated", reason="processing_failed", weights=weights, score=None, dimensions=())
        for item in batch.candidates)
    response = ScoringBatch(job_id=job.id, job_reference=job.job_reference, batch_id=batch.batch_id,
        criteria_revision=job.revision, weights=weights, candidates=candidates, ranking=tuple(score_ranking(candidates)), ai_provenance=provenance)
    type(batch).model_validate({**batch.model_dump(), "scoring": response.model_dump()})
    # The job row lock serializes reruns/revisions. Replace only this exact run;
    # historical revision records remain intact. Commit all candidates together.
    await session.execute(delete(CandidateScoreRecord).where(CandidateScoreRecord.job_id == job.id,
        CandidateScoreRecord.batch_id == batch.batch_id, CandidateScoreRecord.criteria_revision == job.revision,
        CandidateScoreRecord.scoring_version == SCORING_VERSION))
    for candidate in candidates:
        session.add(CandidateScoreRecord(job_id=job.id, batch_id=batch.batch_id, upload_id=candidate.upload_id,
            criteria_revision=job.revision, scoring_version=SCORING_VERSION, score=candidate.score,
            payload={**candidate.model_dump(mode="json"), **({"_ai_provenance": provenance.model_dump() } if provenance else {})}))
    await session.commit()
    return response


async def load_scores(session, job, batch_id):
    if job.confirmed_snapshot is None:
        raise HTTPException(409, "Review and confirm the current criteria and weights first.")
    rows = (await session.scalars(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id == job.id,
        CandidateScoreRecord.batch_id == batch_id, CandidateScoreRecord.criteria_revision == job.revision,
        CandidateScoreRecord.scoring_version == SCORING_VERSION).order_by(CandidateScoreRecord.upload_id).limit(21))).all()
    if not rows:
        raise HTTPException(404, "No scores exist for the current approved job revision and batch.")
    try:
        metadata = [AIProvenance.model_validate(row.payload['_ai_provenance']) if row.payload.get('_ai_provenance') is not None else None for row in rows]
        if any(item != metadata[0] for item in metadata):
            raise ValueError('Inconsistent stored AI provenance.')
        candidates = tuple(restore_candidate_score(row.payload) for row in rows)
        if any(c.upload_id != row.upload_id or c.score != row.score for c, row in zip(candidates, rows)):
            raise ValueError("Stored score association is invalid.")
        return ScoringBatch(job_id=job.id, job_reference=job.job_reference, batch_id=batch_id,
            criteria_revision=job.revision, weights=ScoringWeights.model_validate(job.scoring_weights or {}),
            candidates=candidates, ranking=tuple(score_ranking(candidates)), ai_provenance=metadata[0])
    except (ValueError, TypeError, AttributeError, KeyError):
        raise HTTPException(500, "Saved scores could not be validated.") from None
