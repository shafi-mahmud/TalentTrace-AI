"""Trusted local-demo review snapshots and contact-free batch results."""
from typing import Literal
from uuid import UUID
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.cv_upload import JobReference
from app.schemas.job_description import JobTitle
from app.schemas.screening import ScreeningCriterion, ScreeningDecisionResult
from app.services.screening_ranking import rank_eligible_candidates
from app.services.score_records import ScoringBatch


class ScreeningSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_title: JobTitle
    criteria: list[ScreeningCriterion] = Field(max_length=71)


class ReviewedJobSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    job_reference: JobReference
    job_title: JobTitle
    criteria_confirmed: Literal[True]
    criteria: list[ScreeningCriterion] = Field(min_length=1, max_length=50)

    @field_validator("criteria_confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("Explicit criterion confirmation is required.")
        return value

    @field_validator("job_title")
    @classmethod
    def safe_title(cls, value):
        if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
            raise ValueError("Job titles must be safe single-line text.")
        return value

    @model_validator(mode="after")
    def unique_criteria(self):
        ids = [criterion.criterion_id.casefold() for criterion in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Criterion identifiers must be unique.")
        return self


OverallCoverage = Literal["met", "partially_met", "unmet", "uncertain", "not_evaluated"]


def overall_requirement_coverage(result: ScreeningDecisionResult | None) -> OverallCoverage:
    """Overall coverage of confirmed atoms, independent of the eligibility gate."""
    if result is None:
        return "not_evaluated"
    result = ScreeningDecisionResult.model_validate(result.model_dump(warnings=False))
    if result.status != "decision_complete":
        return "not_evaluated"
    statuses = {match.match_status for match in result.matching_result.matches}
    if "ambiguous" in statuses:
        return "uncertain"
    if statuses == {"supported"}:
        return "met"
    if statuses == {"not_found"}:
        return "unmet"
    return "partially_met"


class BatchScreeningItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    upload_id: UUID
    result: ScreeningDecisionResult | None
    error_code: Literal["screening_processing_failed"] | None
    overall_coverage: OverallCoverage

    @model_validator(mode="after")
    def consistent_item(self):
        if (self.result is None) != (self.error_code is not None):
            raise ValueError("A screening item must have either a result or a processing error.")
        if self.result is not None and self.result.upload_id != self.upload_id:
            raise ValueError("Screening identity must match the upload.")
        if self.overall_coverage != overall_requirement_coverage(self.result):
            raise ValueError("Overall coverage must match the validated requirement evidence.")
        return self


class CandidateRankingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    upload_id: UUID
    rank: int = Field(strict=True, ge=1, le=20)
    supported_count: int = Field(strict=True, ge=0, le=50)
    ambiguous_count: int = Field(strict=True, ge=0, le=50)
    not_found_count: int = Field(strict=True, ge=0, le=50)
    total_requirements: int = Field(strict=True, ge=1, le=50)
    tied: bool = Field(strict=True)

    @model_validator(mode="after")
    def complete_counts(self):
        if self.supported_count + self.ambiguous_count + self.not_found_count != self.total_requirements:
            raise ValueError("Evidence counts must cover all confirmed requirements.")
        return self


class BatchScreeningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["processed"] = "processed"
    job_reference: JobReference
    batch_id: UUID
    snapshot: ReviewedJobSnapshot
    processed_count: int = Field(ge=1, le=20)
    candidates: list[BatchScreeningItem] = Field(min_length=1, max_length=20)
    ranking: list[CandidateRankingEntry] = Field(max_length=20)
    scoring: ScoringBatch | None = None

    @model_validator(mode="after")
    def consistent_batch(self):
        ids = [item.upload_id for item in self.candidates]
        if self.snapshot.job_reference != self.job_reference or self.processed_count != len(ids) or len(set(ids)) != len(ids):
            raise ValueError("Batch identity and count must match the reviewed snapshot.")
        for item in self.candidates:
            if item.result is not None:
                context = item.result.matching_result.requirement_context
                expected = [c.criterion_id for c in self.snapshot.criteria]
                actual = context.skill_ids + context.experience_ids + context.education_ids
                if (item.result.job_reference != self.job_reference or set(actual) != set(expected)
                    or context.hard_requirement_ids != tuple(c.criterion_id for c in self.snapshot.criteria if c.is_hard)):
                    raise ValueError("Results must refer to the confirmed requirements.")
        expected_ranking = rank_eligible_candidates(
            [item.result for item in self.candidates if item.result is not None],
            job_reference=self.job_reference, criteria=self.snapshot.criteria)
        if [entry.model_dump() for entry in self.ranking] != expected_ranking:
            raise ValueError("Ranking must reflect exactly the eligible candidates and confirmed evidence.")
        if self.scoring is not None:
            from app.services.candidate_scoring import score_candidate
            if self.scoring.job_reference != self.job_reference or self.scoring.batch_id != self.batch_id or {c.upload_id for c in self.scoring.candidates} != set(ids):
                raise ValueError("Scoring must match this batch.")
            for item in self.candidates:
                score = next(c for c in self.scoring.candidates if c.upload_id == item.upload_id)
                if item.result is not None and score != score_candidate(item.result, job_reference=self.job_reference,
                    criteria=self.snapshot.criteria, weights=self.scoring.weights):
                    raise ValueError("Scores must reflect validated screening evidence.")
                if item.result is None and score.reason != "processing_failed":
                    raise ValueError("Processing errors must not have scores.")
        return self
