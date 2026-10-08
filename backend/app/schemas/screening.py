"""Preparation and matching evidence contracts; no contact identity or verdicts."""
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.schemas.candidate_profile import CandidateQualifications, ProfileContract, SourceReference, ValueText
from app.schemas.cv_upload import JobReference

CriterionId = Annotated[str, StringConstraints(
    min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
)]
CriterionDescription = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=500,
)]


class ScreeningCriterion(ProfileContract):
    criterion_id: CriterionId
    category: Literal["skill", "experience", "education"]
    description: CriterionDescription = Field(repr=False)
    is_hard: bool

    @field_validator("description", mode="before")
    @classmethod
    def single_line_description(cls, value):
        if isinstance(value, str) and any(
            unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value
        ):
            raise ValueError("Criterion descriptions must be safe single-line text.")
        return value


class ScreeningInput(ProfileContract):
    job_reference: JobReference
    upload_id: UUID
    # Same three statuses as CandidateProfile; no new parsing semantics.
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    qualifications: CandidateQualifications | None = Field(repr=False)
    criteria: tuple[ScreeningCriterion, ...] = Field(min_length=1, max_length=50, repr=False)

    @model_validator(mode="after")
    def consistent_input(self):
        if (self.parsing_status == "parsed") != (self.qualifications is not None):
            raise ValueError("Qualifications must be present only for parsed candidates.")
        ids = [item.criterion_id.casefold() for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion identifiers must be unique.")
        return self


class RequirementContext(ProfileContract):
    """Stable category grouping; IDs identify requirements, not satisfaction."""
    skill_ids: tuple[CriterionId, ...] = Field(max_length=50)
    experience_ids: tuple[CriterionId, ...] = Field(max_length=50)
    education_ids: tuple[CriterionId, ...] = Field(max_length=50)
    hard_requirement_ids: tuple[CriterionId, ...] = Field(max_length=50)

    @model_validator(mode="after")
    def consistent_ids(self):
        ids = self.skill_ids + self.experience_ids + self.education_ids
        if not ids or len(ids) > 50 or len(set(ids)) != len(ids):
            raise ValueError("Requirement groups must contain unique bounded identifiers.")
        if (len(set(self.hard_requirement_ids)) != len(self.hard_requirement_ids)
                or not set(self.hard_requirement_ids).issubset(ids)):
            raise ValueError("Hard requirements must belong to the requirement groups.")
        return self


class ScreeningPreparationResult(ProfileContract):
    job_reference: JobReference
    upload_id: UUID
    status: Literal["ready_for_matching", "source_unavailable"]
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    requirement_context: RequirementContext
    screening_decision: None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "ready_for_matching") != (self.parsing_status == "parsed"):
            raise ValueError("Preparation status must match source readiness.")
        return self


FactId = Annotated[str, StringConstraints(pattern=r"^fact:[0-9]{4}$", max_length=9)]
RecordGroupId = Annotated[str, StringConstraints(
    pattern=r"^(?:education|work):(?:0[1-9]|1[0-9]|20)$", max_length=12,
)]
MatchStatus = Literal["supported", "not_found", "ambiguous"]
MatchingErrorCode = Literal["semantic_not_configured", "semantic_provider_failed",
    "invalid_semantic_response", "semantic_input_limit"]


class QualificationFact(ProfileContract):
    fact_id: FactId
    record_group: RecordGroupId | None
    kind: Literal["skill", "education_qualification", "education_field",
        "work_role", "work_period", "work_activity"]
    value: ValueText = Field(repr=False)
    source: SourceReference

    @model_validator(mode="after")
    def consistent_record_group(self):
        if self.kind == "skill":
            if self.record_group is not None:
                raise ValueError("Standalone skills have no record group.")
        else:
            prefix = "education:" if self.kind.startswith("education_") else "work:"
            if self.record_group is None or not self.record_group.startswith(prefix):
                raise ValueError("Qualification facts require the corresponding record group.")
        return self


class SemanticEvidenceReference(ProfileContract):
    """Provider must copy a value from the referenced supplied fact."""
    fact_id: FactId
    value: ValueText = Field(repr=False)


class SemanticCriterionMatch(ProfileContract):
    criterion_id: CriterionId
    match_status: MatchStatus
    evidence: list[SemanticEvidenceReference] = Field(max_length=8, repr=False)

    @model_validator(mode="after")
    def consistent_evidence(self):
        if (self.match_status == "not_found") != (len(self.evidence) == 0):
            raise ValueError("Supported or ambiguous interpretations require evidence; not_found must have none.")
        if len({e.fact_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Evidence references must be unique.")
        return self


class SemanticMatchingResponse(ProfileContract):
    results: list[SemanticCriterionMatch] = Field(min_length=1, max_length=50, repr=False)


class MatchEvidence(ProfileContract):
    fact_id: FactId
    value: ValueText = Field(repr=False)
    source: SourceReference


class RequirementMatch(ProfileContract):
    criterion_id: CriterionId
    match_status: MatchStatus
    match_method: Literal["deterministic", "semantic"]
    evidence: tuple[MatchEvidence, ...] = Field(max_length=8, repr=False)
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=300)]

    @model_validator(mode="after")
    def consistent_evidence(self):
        if (self.match_status == "not_found") != (len(self.evidence) == 0):
            raise ValueError("Match status must agree with evidence availability.")
        if len({e.fact_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Evidence references must be unique.")
        return self


class ScreeningMatchingResult(ProfileContract):
    job_reference: JobReference
    upload_id: UUID
    status: Literal["matching_complete", "source_unavailable", "matching_failed"]
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    requirement_context: RequirementContext
    matches: tuple[RequirementMatch, ...] = Field(max_length=50, repr=False)
    error_code: MatchingErrorCode | None
    screening_decision: None = None

    @model_validator(mode="after")
    def consistent_result(self):
        if (self.status == "source_unavailable") != (self.parsing_status != "parsed"):
            raise ValueError("Result status must agree with source status.")
        if self.status == "matching_complete":
            expected = (self.requirement_context.skill_ids + self.requirement_context.experience_ids
                + self.requirement_context.education_ids)
            actual = [match.criterion_id for match in self.matches]
            if self.error_code is not None or len(actual) != len(expected) or set(actual) != set(expected):
                raise ValueError("Completed matching requires exactly one result per criterion.")
        elif self.matches or (self.status == "matching_failed") != (self.error_code is not None):
            raise ValueError("Incomplete matching must not contain evidence conclusions.")
        return self
