from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag.contracts import (
    COMPANY_POLICY_COLLECTION,
    CompanyPolicySource,
    PolicyChunk,
    PolicyChunkMetadata,
    chunk_sha256,
)


class TokenCounter(Protocol):
    """Counts tokens using an implementation supplied by the caller."""

    def count_tokens(self, text: str) -> int:
        """Return the token count for text without changing it."""


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_size_tokens: int = Field(default=700, strict=True, ge=500, le=800)
    overlap_tokens: int = Field(default=75, strict=True, ge=50, le=100)

    @model_validator(mode="after")
    def overlap_must_be_smaller_than_chunk(self) -> "ChunkingConfig":
        if self.overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("overlap_tokens must be smaller than chunk_size_tokens")
        return self


@dataclass(frozen=True)
class _Section:
    heading_path: tuple[str, ...]
    body: str


@dataclass(frozen=True)
class _Unit:
    text: str
    heading_paths: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class _DraftChunk:
    text: str
    heading_paths: tuple[tuple[str, ...], ...]
    token_count: int


_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.{1,200}?)\s*#*$")
_NUMBERED_HEADING = re.compile(
    r"^(?P<number>[0-9]+(?:\.[0-9]+)*)[.)]?\s+(?P<title>.{1,180})$"
)


def chunk_company_policy(
    source: CompanyPolicySource,
    token_counter: TokenCounter,
    config: ChunkingConfig | None = None,
) -> tuple[PolicyChunk, ...]:
    """Split normalized policy text into deterministic, cited chunks."""

    active_config = config or ChunkingConfig()
    max_unit_tokens = (
        active_config.chunk_size_tokens - active_config.overlap_tokens
    )
    sections = _parse_sections(source.text)
    units = tuple(
        unit
        for section in sections
        for unit in _section_units(section, max_unit_tokens, token_counter)
    )

    drafts = _assemble_chunks(units, token_counter, active_config)
    if not drafts:
        raise ValueError(
            "Company policy contains no chunkable content after heading parsing."
        )

    return tuple(
        _create_chunk(source, draft, index)
        for index, draft in enumerate(drafts)
    )


def _parse_sections(text: str) -> tuple[_Section, ...]:
    sections: list[_Section] = []
    heading_stack: list[str] = []
    active_heading_path: tuple[str, ...] = ()
    body_lines: list[str] = []

    def flush_section() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append(_Section(active_heading_path, body))
        body_lines.clear()

    for line in text.split("\n"):
        heading = _heading(line)
        if heading is None:
            body_lines.append(line)
            continue

        flush_section()
        level, title = heading
        heading_stack = heading_stack[: level - 1]
        heading_stack.append(title)
        active_heading_path = tuple(heading_stack)

    flush_section()
    return tuple(sections)


def _heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return None

    markdown_match = _MARKDOWN_HEADING.fullmatch(stripped)
    if markdown_match:
        return len(markdown_match.group(1)), markdown_match.group(2).strip()

    numbered_match = _NUMBERED_HEADING.fullmatch(stripped)
    if numbered_match:
        number = numbered_match.group("number")
        return number.count(".") + 1, numbered_match.group("title").strip()

    letters = [character for character in stripped if character.isalpha()]
    if letters and len(stripped) <= 120 and stripped.upper() == stripped:
        return 1, stripped

    return None


def _section_units(
    section: _Section,
    max_tokens: int,
    token_counter: TokenCounter,
) -> tuple[_Unit, ...]:
    heading_prefix = _heading_prefix(section.heading_path)
    complete_text = _with_heading(heading_prefix, section.body)

    if _count_tokens(token_counter, complete_text) <= max_tokens:
        return (_Unit(complete_text, _paths_for(section.heading_path)),)

    pieces = _split_body_with_heading(
        section.body,
        heading_prefix,
        max_tokens,
        token_counter,
    )
    heading_paths = _paths_for(section.heading_path)
    return tuple(_Unit(piece, heading_paths) for piece in pieces)


def _split_body_with_heading(
    body: str,
    heading_prefix: str,
    max_tokens: int,
    token_counter: TokenCounter,
) -> tuple[str, ...]:
    words = body.split()
    pieces: list[str] = []
    start = 0

    while start < len(words):
        low = start + 1
        high = len(words)
        best_end: int | None = None

        while low <= high:
            middle = (low + high) // 2
            candidate = _with_heading(
                heading_prefix,
                " ".join(words[start:middle]),
            )
            if _count_tokens(token_counter, candidate) <= max_tokens:
                best_end = middle
                low = middle + 1
            else:
                high = middle - 1

        if best_end is None:
            raise ValueError(
                "A policy text segment cannot fit within the configured chunk size."
            )

        pieces.append(
            _with_heading(heading_prefix, " ".join(words[start:best_end]))
        )
        start = best_end

    return tuple(pieces)


def _assemble_chunks(
    units: tuple[_Unit, ...],
    token_counter: TokenCounter,
    config: ChunkingConfig,
) -> tuple[_DraftChunk, ...]:
    drafts: list[_DraftChunk] = []
    current_text_parts: list[str] = []
    current_heading_paths: list[tuple[str, ...]] = []

    for unit in units:
        candidate = _join_parts((*current_text_parts, unit.text))
        if current_text_parts and (
            _count_tokens(token_counter, candidate) > config.chunk_size_tokens
        ):
            previous = _draft_chunk(
                current_text_parts,
                current_heading_paths,
                token_counter,
            )
            drafts.append(previous)

            overlap = _overlap_for_next_chunk(
                previous.text,
                unit.text,
                token_counter,
                config,
            )
            current_text_parts = [overlap] if overlap else []
            current_heading_paths = list(previous.heading_paths) if overlap else []

        current_text_parts.append(unit.text)
        current_heading_paths.extend(unit.heading_paths)

    if current_text_parts:
        drafts.append(
            _draft_chunk(
                current_text_parts,
                current_heading_paths,
                token_counter,
            )
        )

    return tuple(drafts)


def _overlap_for_next_chunk(
    previous_text: str,
    next_text: str,
    token_counter: TokenCounter,
    config: ChunkingConfig,
) -> str:
    words = previous_text.split()
    low = 0
    high = len(words)
    best = ""

    while low <= high:
        word_count = (low + high) // 2
        candidate = " ".join(words[-word_count:]) if word_count else ""
        combined = _join_parts((candidate, next_text))
        overlap_count = _count_tokens(token_counter, candidate) if candidate else 0

        if (
            overlap_count <= config.overlap_tokens
            and _count_tokens(token_counter, combined) <= config.chunk_size_tokens
        ):
            best = candidate
            low = word_count + 1
        else:
            high = word_count - 1

    return best


def _draft_chunk(
    parts: list[str],
    heading_paths: list[tuple[str, ...]],
    token_counter: TokenCounter,
) -> _DraftChunk:
    text = _join_parts(tuple(parts))
    return _DraftChunk(
        text=text,
        heading_paths=_unique_paths(heading_paths),
        token_count=_count_tokens(token_counter, text),
    )


def _create_chunk(
    source: CompanyPolicySource,
    draft: _DraftChunk,
    index: int,
) -> PolicyChunk:
    digest = chunk_sha256(draft.text)
    version_fingerprint = hashlib.sha256(
        source.source_version.encode("utf-8")
    ).hexdigest()[:16]
    citation_id = (
        f"policy:{source.source_id.hex}:{version_fingerprint}:"
        f"{source.content_sha256[:16]}:{index:04d}"
    )
    metadata = PolicyChunkMetadata(
        collection=COMPANY_POLICY_COLLECTION,
        citation_id=citation_id,
        source_id=source.source_id,
        source_version=source.source_version,
        source_content_sha256=source.content_sha256,
        chunk_index=index,
        chunk_sha256=digest,
        token_count=draft.token_count,
        heading_paths=draft.heading_paths,
    )
    return PolicyChunk(text=draft.text, metadata=metadata)


def _heading_prefix(heading_path: tuple[str, ...]) -> str:
    if not heading_path:
        return ""
    return f"Heading: {' > '.join(heading_path)}"


def _with_heading(heading_prefix: str, body: str) -> str:
    if not heading_prefix:
        return body
    return f"{heading_prefix}\n\n{body}"


def _paths_for(heading_path: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return (heading_path,) if heading_path else ()


def _join_parts(parts: tuple[str, ...]) -> str:
    return "\n\n".join(part for part in parts if part)


def _unique_paths(
    paths: list[tuple[str, ...]],
) -> tuple[tuple[str, ...], ...]:
    return tuple(dict.fromkeys(paths))


def _count_tokens(token_counter: TokenCounter, text: str) -> int:
    count = token_counter.count_tokens(text)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("Token counter must return a non-negative integer.")
    return count
