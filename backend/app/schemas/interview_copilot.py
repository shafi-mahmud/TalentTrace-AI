"""Synthetic live-event contracts, independent of stored transcript identities."""
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

CriterionId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')]
Kind = Literal['explore', 'example', 'clarify']
ExplorationState = Literal['not_observed', 'question_observed', 'response_observed', 'uncertain_association']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True,
                              revalidate_instances='always')


def safe_text(value):
    if any(unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} for c in value):
        raise ValueError('Single-line text required.')
    return value.strip()


class Requirement(Contract):
    id: CriterionId
    description: str = Field(min_length=1, max_length=500, repr=False)

    @field_validator('description')
    @classmethod
    def description_text(cls, value):
        result = safe_text(value)
        if not result:
            raise ValueError('A requirement description is required.')
        return result


class Binding(Contract):
    interview_id: UUID
    run_id: UUID
    caption_run_id: UUID
    criteria_revision: int = Field(ge=1)
    requirements: tuple[Requirement, ...] = Field(min_length=1, max_length=50, repr=False)

    @model_validator(mode='after')
    def unique_requirements(self):
        ids = [r.id.casefold() for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError('Requirement identities must be unique.')
        return self


class Source(Contract):
    caption_run_id: UUID
    sequence: int = Field(ge=1)


class Event(Contract):
    interview_id: UUID
    run_id: UUID
    criteria_revision: int = Field(ge=1)
    generation: int = Field(ge=1)
    source: Source
    role: Literal['recruiter', 'candidate']
    timestamp_ms: int = Field(ge=0)
    text: str = Field(max_length=1000, repr=False)

    @field_validator('text')
    @classmethod
    def recognized_text(cls, value):
        return safe_text(value)


class Update(Contract):
    synthetic: Literal[True]
    binding: Binding
    generation: int = Field(ge=1)
    events: tuple[Event, ...] = Field(max_length=15, repr=False)

    @model_validator(mode='after')
    def character_bound(self):
        if sum(len(e.text) for e in self.events) > 12000:
            raise ValueError('Context character limit exceeded.')
        return self


class Exploration(Contract):
    criterion_id: CriterionId
    state: ExplorationState
    sources: tuple[Source, ...] = Field(max_length=15)


class Suggestion(Contract):
    criterion_id: CriterionId
    kind: Kind
    question: str = Field(min_length=1, max_length=700, repr=False)
    sources: tuple[Source, ...] = Field(min_length=1, max_length=15)
    provisional: Literal[True] = True


class Result(Contract):
    status: Literal['suggested', 'waiting', 'abstained', 'rejected']
    reason: Literal['valid_suggestion', 'context_unavailable', 'invalid_context', 'stale_generation',
                    'source_conflict', 'context_expired', 'fragments_pending', 'insufficient_context',
                    'ambiguous_association', 'cooldown', 'already_seen', 'unsupported_output']
    generation: int = Field(ge=0)
    exploration: tuple[Exploration, ...] = ()
    suggestions: tuple[Suggestion, ...] = Field(default=(), max_length=3)
