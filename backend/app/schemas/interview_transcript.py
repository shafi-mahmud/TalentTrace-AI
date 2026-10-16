"""Internal final-event contract, deliberately not exposed by an API."""
import unicodedata
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FinalTranscriptEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    id: UUID
    session_id: UUID
    sequence: int = Field(ge=1, le=2147483647)
    role: Literal['recruiter', 'candidate']
    final: Literal[True]
    text: str = Field(min_length=1, max_length=1000, repr=False)
    start_ms: int = Field(ge=0, le=2147483647)
    end_ms: int = Field(ge=0, le=2147483647)

    @field_validator('final', mode='before')
    @classmethod
    def final_only(cls, value):
        if value is not True:
            raise ValueError('A final recognition event is required.')
        return value

    @field_validator('text')
    @classmethod
    def safe_text(cls, value):
        if not value.strip() or any(unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} for c in value):
            raise ValueError('Invalid recognized text.')
        return value

    @model_validator(mode='after')
    def ordered_time(self):
        if self.end_ms < self.start_ms:
            raise ValueError('Invalid recognition interval.')
        return self


class SampleCounts(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    recruiter: int = Field(ge=0, le=4800000)
    candidate: int = Field(ge=0, le=4800000)


class CaptureEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    audio_outcome: Literal['drained','partial','failed']
    expected_turns: int = Field(ge=0, le=150)
    acknowledged_turns: int = Field(ge=0, le=150)
    accepted_samples: SampleCounts
    processed_samples: SampleCounts
    scope: Literal['accepted_audio_only']
    commit_uncertain: bool
