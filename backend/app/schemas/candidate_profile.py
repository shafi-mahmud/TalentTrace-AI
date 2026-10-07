"""Private provider evidence and separate public, source-backed candidate facts."""
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.cv_extraction import ExtractionContract
from app.schemas.cv_upload import JobReference

MAX_PARSER_CHARS = 40_000
MAX_PARSER_UNITS = 400
ValueText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
SourceId = Annotated[str, StringConstraints(pattern=r"^(?:page|block):[1-9][0-9]{0,4}$", max_length=11)]


class ProfileContract(ExtractionContract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    @field_validator("*", mode="before")
    @classmethod
    def safe_strings(cls, value):
        if isinstance(value, str):
            if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\n\r\t" for c in value):
                raise ValueError("Unsafe text characters.")
            return unicodedata.normalize("NFC", value)
        return value


class SourceReference(ProfileContract):
    kind: Literal["page", "block"]
    number: int = Field(ge=1, le=10_000)
    method: Literal["digital", "ocr"]
    block_type: Literal["paragraph", "table_cell"] | None = None

    @model_validator(mode="after")
    def consistent_locator(self):
        if self.kind == "page" and (self.number > 200 or self.block_type is not None):
            raise ValueError("Invalid page locator.")
        if self.kind == "block" and (self.method != "digital" or self.block_type is None):
            raise ValueError("Invalid block locator.")
        return self


class CandidateSourceUnit(ProfileContract):
    source_id: SourceId
    source: SourceReference
    text: str = Field(max_length=MAX_PARSER_CHARS, repr=False)


class CandidateSourceDocument(ProfileContract):
    upload_id: UUID
    units: tuple[CandidateSourceUnit, ...] = Field(min_length=1, max_length=MAX_PARSER_UNITS, repr=False)

    @model_validator(mode="after")
    def bounded_evidence(self):
        if sum(len(unit.text) for unit in self.units) + 2 * (len(self.units) - 1) > MAX_PARSER_CHARS:
            raise ValueError("Candidate input exceeds parser limit.")
        ids = [unit.source_id for unit in self.units]
        if len(set(ids)) != len(ids) or any(unit.source_id != f"{unit.source.kind}:{unit.source.number}" for unit in self.units):
            raise ValueError("Invalid source identifiers.")
        return self


class EvidenceValue(ProfileContract):
    value: ValueText = Field(repr=False)
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] = Field(repr=False)
    source_id: SourceId


class ContactInterpretation(ProfileContract):
    candidate_name: EvidenceValue | None
    emails: list[EvidenceValue] = Field(max_length=5)
    phones: list[EvidenceValue] = Field(max_length=5)
    links: list[EvidenceValue] = Field(max_length=10)
    location: EvidenceValue | None


class EducationInterpretation(ProfileContract):
    institution: EvidenceValue | None
    qualification: EvidenceValue | None
    field_of_study: EvidenceValue | None
    date_or_period: EvidenceValue | None


class WorkInterpretation(ProfileContract):
    employer: EvidenceValue | None
    role_title: EvidenceValue | None
    date_or_period: EvidenceValue | None
    location: EvidenceValue | None
    responsibilities_or_achievements: list[EvidenceValue] = Field(max_length=20)


class QualificationsInterpretation(ProfileContract):
    education: list[EducationInterpretation] = Field(max_length=20)
    work_history: list[WorkInterpretation] = Field(max_length=20)
    skills: list[EvidenceValue] = Field(max_length=100)


class CandidateProfileInterpretation(ProfileContract):
    """All properties required for strict provider JSON schema; null/[] means absent."""
    contact: ContactInterpretation = Field(repr=False)
    qualifications: QualificationsInterpretation = Field(repr=False)


class GroundedAttribute(ProfileContract):
    value: ValueText = Field(repr=False)
    source: SourceReference


class CandidateContact(ProfileContract):
    candidate_name: GroundedAttribute | None
    emails: list[GroundedAttribute] = Field(max_length=5)
    phones: list[GroundedAttribute] = Field(max_length=5)
    links: list[GroundedAttribute] = Field(max_length=10)
    location: GroundedAttribute | None


class CandidateEducation(ProfileContract):
    institution: GroundedAttribute | None
    qualification: GroundedAttribute | None
    field_of_study: GroundedAttribute | None
    date_or_period: GroundedAttribute | None


class CandidateWorkHistory(ProfileContract):
    employer: GroundedAttribute | None
    role_title: GroundedAttribute | None
    date_or_period: GroundedAttribute | None
    location: GroundedAttribute | None
    responsibilities_or_achievements: list[GroundedAttribute] = Field(max_length=20)


class CandidateQualifications(ProfileContract):
    education: list[CandidateEducation] = Field(max_length=20)
    work_history: list[CandidateWorkHistory] = Field(max_length=20)
    skills: list[GroundedAttribute] = Field(max_length=100)


class CandidateProfile(ProfileContract):
    upload_id: UUID
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    contact: CandidateContact | None = Field(repr=False)
    qualifications: CandidateQualifications | None = Field(repr=False)

    @model_validator(mode="after")
    def consistent_status(self):
        complete = self.contact is not None and self.qualifications is not None
        if self.parsing_status == "parsed" and not complete:
            raise ValueError("Parsed profiles require both sections.")
        if self.parsing_status != "parsed" and (self.contact is not None or self.qualifications is not None):
            raise ValueError("Failed profiles must not contain candidate facts.")
        return self


class CandidateProfilesResponse(ProfileContract):
    status: Literal["processed"] = "processed"
    job_reference: JobReference
    batch_id: UUID
    processed_count: int = Field(ge=1, le=20)
    candidates: tuple[CandidateProfile, ...] = Field(min_length=1, max_length=20, repr=False)

    @model_validator(mode="after")
    def consistent_count(self):
        if self.processed_count != len(self.candidates):
            raise ValueError("Profile count must match candidate results.")
        return self
