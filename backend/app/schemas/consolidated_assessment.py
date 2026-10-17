"""F6 Increment 1: existing evidence only; no combined suitability score."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.schemas.candidate_score import CandidateScore
from app.schemas.screening import ScreeningCriterion
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
    # Empty when the original confirmed revision cannot be established. Never
    # relabel a historical selection using today's mutable job descriptions.
    confirmed_requirements: tuple[ScreeningCriterion, ...] = ()
    interview: InterviewEvidence
    review_required: Literal[True] = True
    notice: str = ('Recruiter review required. F2 measures demonstrated CV requirement coverage; '
                   'F5 is advisory and ASR is unverified. Missing evidence is not poor performance. '
                   'No combined score or suitability decision is calculated.')


class CandidateComparison(Contract):
    version: Literal['f6-comparison-1'] = 'f6-comparison-1'
    job_id: UUID
    criteria_revision: int
    reports: tuple[ConsolidatedAssessment, ConsolidatedAssessment]
    review_required: Literal[True] = True
    notice: str = ('Same-job saved evidence only. Different interviews may assess different questions. '
                   'Missing evidence is not poor performance. No combined score, ranking or hiring recommendation.')


class DiscoveredApplication(Contract):
    job_id: UUID
    batch_id: UUID
    upload_id: UUID
    kind: Literal['scored', 'unscored', 'historical_snapshot', 'unavailable']
    label: str
    detail: str
    evidence_revision: int | None = None
    recorded_revisions: tuple[int, ...] = ()
    report_available: bool = False
    comparison_available: bool = False


class ApplicationDiscovery(Contract):
    job_id: UUID
    criteria_revision: int
    applications: tuple[DiscoveredApplication, ...]
    notice: str = ('Persisted score, selection snapshot and local intake-ledger records only. '
                   'Unscreened filesystem-only uploads are not an application registry. '
                   'Discovery does not authorize interview evidence; each report revalidates access.')
