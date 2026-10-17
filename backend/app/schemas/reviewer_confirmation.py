"""Bounded reviewer input: codes and IDs only, never free text or source copies."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.screening import CriterionId

Position = Literal['alignment', 'mixed', 'insufficient']
Reason = Literal['supported_requirement', 'documented_concern', 'uncertain_finding', 'missing_evidence']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, hide_input_in_errors=True)


class EvidenceReference(Contract):
    criterion_id: CriterionId
    kind: Literal['cv', 'interview', 'gap']
    reason: Reason
    qa_id: UUID | None = None
    dimension: Literal['relevance', 'technical_accuracy', 'completeness', 'articulation'] | None = None

    @model_validator(mode='after')
    def association(self):
        if (self.kind == 'interview') != (self.qa_id is not None and self.dimension is not None):
            raise ValueError('Interview references need exact question and dimension.')
        if self.kind != 'interview' and (self.qa_id is not None or self.dimension is not None):
            raise ValueError('Unexpected interview reference.')
        if self.kind == 'gap' and self.reason != 'missing_evidence':
            raise ValueError('A gap is not a performance concern.')
        return self


class ConfirmationInput(Contract):
    expected_version: int = Field(ge=0, strict=True)
    evidence_token: str = Field(pattern=r'^[0-9a-f]{64}$')
    position: Position
    scope: Literal['cv_only', 'cv_interview']
    requirement_ids: list[CriterionId] = Field(min_length=1, max_length=50)
    references: list[EvidenceReference] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_scope(self):
        if len(set(self.requirement_ids)) != len(self.requirement_ids):
            raise ValueError('Repeated scope requirements.')
        if len({r.model_dump_json() for r in self.references}) != len(self.references):
            raise ValueError('Repeated evidence references.')
        return self


class ConfirmationView(Contract):
    enabled: bool = False
    state: Literal['pending', 'stale', 'restricted', 'confirmed'] = 'pending'
    version: int = 0
    evidence_token: str | None = None
    position: Position | None = None
    scope: Literal['cv_only', 'cv_interview'] | None = None
    requirement_ids: list[CriterionId] = []
    references: list[EvidenceReference] = []
    reviewer_id: UUID | None = None
    confirmed_at: datetime | None = None
    expires_at: datetime | None = None
