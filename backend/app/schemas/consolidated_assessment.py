"""F6 Increment 1: existing evidence only; no combined suitability score."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.schemas.candidate_score import CandidateScore
from app.services.interview_qa import QAPair
from app.services.interview_mapping import RequirementMapping, TechnicalReference
from app.agents.evaluation.workflow import ModelAssessment
from app.schemas.interview_transcript import FinalTranscriptEvent


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, hide_input_in_errors=True)


class InterviewEvidence(Contract):
    state: Literal['available', 'not_scheduled', 'disabled', 'withdrawn', 'expired',
                   'deleted', 'stale', 'missing_analysis', 'pending', 'unavailable', 'ambiguous']
    interview_id: UUID | None = None
    operation_id: UUID | None = None
    rubric_version: str | None = None
    retention_deadline: datetime | None = None
    warning: str | None = None
    pairs: tuple[QAPair, ...] = ()
    requirements: tuple[RequirementMapping, ...] = ()
    assessment: ModelAssessment | None = None
    references: tuple[TechnicalReference, ...] = ()
    turns: tuple[FinalTranscriptEvent, ...] = ()


class ConsolidatedAssessment(Contract):
    version: Literal['f6-increment-1'] = 'f6-increment-1'
    job_id: UUID
    job_title: str
    job_reference: str
    batch_id: UUID
    upload_id: UUID
    criteria_revision: int
    cv_source: Literal['current_saved_score', 'interview_selection_snapshot']
    cv: CandidateScore
    interview: InterviewEvidence
    review_required: Literal[True] = True
    notice: str = ('Recruiter review required. F2 measures demonstrated CV requirement coverage; '
                   'F5 is advisory and ASR is unverified. Missing evidence is not poor performance. '
                   'No combined score or suitability decision is calculated.')
