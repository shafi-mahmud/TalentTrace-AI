from __future__ import annotations

import hashlib
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
)


COMPANY_POLICY_COLLECTION = "company_policy"
RetrievalMode = Literal["deterministic_lexical_demo", "semantic_bge_pgvector"]
MAX_POLICY_TEXT_LENGTH = 500_000

SourceVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
PolicyTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
]
Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
CitationId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=180,
        pattern=(
            r"^policy:[0-9a-f]{32}:"
            r"[0-9a-f]{16}:[0-9a-f]{16}:[0-9]{4,}$"
        ),
    ),
]
Heading = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


def _normalize_policy_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\t", "    ")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return normalized.strip()


def _contains_unsafe_control_character(
    value: str,
    *,
    allow_newline: bool,
) -> bool:
    return any(
        not (allow_newline and character == "\n")
        and unicodedata.category(character) in {"Cc", "Cs"}
        for character in value
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CompanyPolicySource(BaseModel):
    """Validated, already-extracted company-policy text."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    collection: Literal["company_policy"] = COMPANY_POLICY_COLLECTION
    source_id: UUID
    source_version: SourceVersion
    title: PolicyTitle
    text: Annotated[str, Field(min_length=1, max_length=MAX_POLICY_TEXT_LENGTH)]

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return _normalize_policy_text(value)
        return value

    @field_validator("title")
    @classmethod
    def reject_unsafe_title_characters(cls, value: str) -> str:
        if _contains_unsafe_control_character(value, allow_newline=False):
            raise ValueError("must not contain null or unsafe control characters")
        return value

    @field_validator("text")
    @classmethod
    def reject_unsafe_text_characters(cls, value: str) -> str:
        if _contains_unsafe_control_character(value, allow_newline=True):
            raise ValueError("must not contain null or unsafe control characters")
        return value

    @computed_field(return_type=str)
    @property
    def content_sha256(self) -> str:
        return _sha256(self.text)

    def source_metadata(self) -> PolicySourceMetadata:
        return PolicySourceMetadata(
            source_id=self.source_id,
            source_version=self.source_version,
            title=self.title,
            content_sha256=self.content_sha256,
        )


class PolicySourceMetadata(BaseModel):
    """Safe identity metadata for one normalized policy source version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection: Literal["company_policy"] = COMPANY_POLICY_COLLECTION
    source_id: UUID
    source_version: SourceVersion
    title: PolicyTitle
    content_sha256: Sha256Digest

    @field_validator("title")
    @classmethod
    def reject_unsafe_control_characters(cls, value: str) -> str:
        if _contains_unsafe_control_character(value, allow_newline=False):
            raise ValueError("must not contain null or unsafe control characters")
        return value


class PolicyChunkMetadata(BaseModel):
    """Citation metadata retained with a derived policy chunk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection: Literal["company_policy"] = COMPANY_POLICY_COLLECTION
    citation_id: CitationId
    source_id: UUID
    source_version: SourceVersion
    source_content_sha256: Sha256Digest
    chunk_index: Annotated[int, Field(strict=True, ge=0)]
    chunk_sha256: Sha256Digest
    token_count: Annotated[int, Field(strict=True, ge=1, le=800)]
    heading_paths: tuple[tuple[Heading, ...], ...] = ()

    @field_validator("heading_paths")
    @classmethod
    def reject_unsafe_heading_characters(
        cls,
        value: tuple[tuple[str, ...], ...],
    ) -> tuple[tuple[str, ...], ...]:
        if any(
            _contains_unsafe_control_character(heading, allow_newline=False)
            for path in value
            for heading in path
        ):
            raise ValueError("headings must not contain unsafe control characters")
        return value


class PolicyChunk(BaseModel):
    """Immutable text chunk and its safe citation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[str, Field(min_length=1, max_length=MAX_POLICY_TEXT_LENGTH)]
    metadata: PolicyChunkMetadata

    @field_validator("text")
    @classmethod
    def reject_unsafe_control_characters(cls, value: str) -> str:
        if _contains_unsafe_control_character(value, allow_newline=True):
            raise ValueError("must not contain null or unsafe control characters")
        return value


def chunk_sha256(text: str) -> str:
    return _sha256(text)
