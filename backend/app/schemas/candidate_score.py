"""Internal F2 foundation; no change to existing screening/checkpoint contracts."""
from typing import Literal
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.cv_upload import JobReference
from app.schemas.screening import RequirementMatch, ScreeningOutcome


class ScoringWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    skill: int = Field(default=50, ge=0, le=100)
    experience: int = Field(default=30, ge=0, le=100)
    education: int = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def total(self):
        if self.skill + self.experience + self.education != 100:
            raise ValueError("Scoring weights must total 100 percent.")
        return self


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    category: Literal["skill", "experience", "education"]
    weight: int = Field(ge=0, le=100)
    supported_count: int = Field(ge=0, le=50)
    total_requirements: int = Field(ge=0, le=50)
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    weighted_points: float | None = Field(default=None, ge=0, le=100)
    # Original validated explanations and source references, not new LLM prose.
    matches: tuple[RequirementMatch, ...] = Field(max_length=50, repr=False)

    @model_validator(mode="after")
    def evidence_counts(self):
        if self.total_requirements != len(self.matches) or self.supported_count != sum(m.match_status == "supported" for m in self.matches):
            raise ValueError("Dimension counts must match existing evidence.")
        ratio = Decimal(self.supported_count) / self.total_requirements if self.total_requirements else None
        expected_coverage = float((100 * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if ratio is not None else None
        expected_points = float((self.weight * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if ratio is not None else 0
        if self.coverage_percent != expected_coverage or self.weighted_points != expected_points:
            raise ValueError("Breakdown must reflect demonstrated coverage.")
        return self


class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_reference: JobReference
    upload_id: UUID
    screening_decision: ScreeningOutcome | None
    status: Literal["scored", "not_evaluated"]
    reason: Literal["processing_failed", "screening_incomplete", "not_eligible", "uncertain_evidence", "missing_dimension_criteria"] | None
    weights: ScoringWeights
    score: float | None = Field(ge=0, le=100)
    dimensions: tuple[DimensionScore, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def available_score(self):
        if self.status == "scored":
            if self.reason is not None or self.score is None or self.screening_decision != "eligible" or len(self.dimensions) != 3:
                raise ValueError("Only complete eligible evidence can have a score.")
            if tuple(d.category for d in self.dimensions) != ("skill", "experience", "education"):
                raise ValueError("Breakdown must contain each dimension once.")
            total = Decimal(0)
            for dimension in self.dimensions:
                if dimension.weight != getattr(self.weights, dimension.category):
                    raise ValueError("Breakdown must use configured weights.")
                if dimension.weight:
                    if not dimension.matches or any(m.match_status == "ambiguous" for m in dimension.matches):
                        raise ValueError("Weighted dimensions require certain evidence.")
                    total += Decimal(dimension.weight) * dimension.supported_count / dimension.total_requirements
            if self.score != float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)):
                raise ValueError("Total must reflect unrounded weighted coverage.")
        elif self.reason is None or self.score is not None or self.dimensions:
            raise ValueError("Unavailable scores must not contain fabricated breakdowns.")
        return self
