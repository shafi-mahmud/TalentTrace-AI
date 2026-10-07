from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from numbers import Real
from threading import Lock
from typing import Protocol


BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
BGE_EMBEDDING_DIMENSION = 384
BGE_MAX_SEQUENCE_TOKENS = 512
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
EmbeddingVector = tuple[float, ...]


class EmbeddingError(ValueError):
    """A controlled embedding failure that never includes the input text."""


class EmbeddingService(Protocol):
    """Local embedding boundary, independent of persistence and retrieval."""

    def embed_documents(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        """Return one normalized vector per passage, in input order."""

    def embed_query(self, text: str) -> EmbeddingVector:
        """Return one normalized vector for a retrieval query."""


class TokenizerBackend(Protocol):
    def encode(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> list[int]:
        """Return tokenizer IDs without silently truncating text."""


class EmbeddingBackend(Protocol):
    tokenizer: TokenizerBackend

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
        prompt: str,
    ) -> object:
        """Small injectable boundary around SentenceTransformer encoding."""


def _load_bge_backend() -> EmbeddingBackend:
    # Importing the application must not import ML libraries or download a model.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        BGE_MODEL_NAME,
        device="cpu",
        trust_remote_code=False,
        token=False,
        model_kwargs={"use_safetensors": True},
    )


class BGEEmbeddingService:
    """Lazy local BGE encoder; output contains only immutable Python tuples."""

    def __init__(
        self, *, backend_factory: Callable[[], EmbeddingBackend] | None = None
    ) -> None:
        self._backend_factory = backend_factory or _load_bge_backend
        self._backend: EmbeddingBackend | None = None
        self._load_lock = Lock()

    def embed_documents(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence) or not texts:
            raise EmbeddingError("Provide at least one non-empty document text.")
        passages = [_validate_text(text) for text in texts]
        return self._embed(passages)

    def embed_query(self, text: str) -> EmbeddingVector:
        query = BGE_QUERY_INSTRUCTION + _validate_text(text)
        return self._embed([query])[0]

    def _get_backend(self) -> EmbeddingBackend:
        with self._load_lock:
            if self._backend is None:
                try:
                    self._backend = self._backend_factory()
                except Exception:
                    raise EmbeddingError("The local BGE model could not be loaded.") from None
            return self._backend

    def _token_ids(self, text: str, *, add_special_tokens: bool) -> list[int]:
        if not isinstance(text, str):
            raise EmbeddingError("Token counting requires text.")
        try:
            raw_ids = self._get_backend().tokenizer.encode(
                text, add_special_tokens=add_special_tokens, truncation=False
            )
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("The BGE tokenizer could not count tokens.") from None
        if not isinstance(raw_ids, list) or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in raw_ids
        ):
            raise EmbeddingError("The BGE tokenizer returned invalid token IDs.")
        return raw_ids

    def _embed(self, texts: list[str]) -> tuple[EmbeddingVector, ...]:
        # Count the query instruction and special tokens too. Never silently
        # truncate a passage: later semantic chunking will supply smaller inputs.
        if any(
            len(self._token_ids(text, add_special_tokens=True)) > BGE_MAX_SEQUENCE_TOKENS
            for text in texts
        ):
            raise EmbeddingError("Embedding text exceeds the BGE token limit.")
        try:
            raw_vectors = self._get_backend().encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                prompt="",  # Disable automatic model prompts; prefix queries ourselves.
            )
        except Exception:
            raise EmbeddingError("The local BGE model could not encode text.") from None
        rows = _items(raw_vectors)
        if len(rows) != len(texts):
            raise EmbeddingError("The BGE model returned an unexpected vector count.")
        return tuple(_validated_vector(row) for row in rows)


class BGETokenCounter:
    """Implements chunking.TokenCounter using BGE tokens, not whitespace words.

    Share a BGEEmbeddingService to reuse its lazily loaded model and tokenizer.
    Counts exclude special tokens; embedding checks separately include them.
    This counter is not wired into the current lexical demo chunker.
    """

    def __init__(self, service: BGEEmbeddingService | None = None) -> None:
        self._service = service if service is not None else BGEEmbeddingService()

    def count_tokens(self, text: str) -> int:
        return len(self._service._token_ids(text, add_special_tokens=False))


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise EmbeddingError("Embedding input must be non-empty text.")
    return text


def _items(value: object) -> list[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise EmbeddingError("The BGE model returned an invalid vector structure.")
    try:
        return list(value)
    except Exception:
        raise EmbeddingError("The BGE model returned an invalid vector structure.") from None


def _validated_vector(value: object) -> EmbeddingVector:
    values = _items(value)
    if len(values) != BGE_EMBEDDING_DIMENSION:
        raise EmbeddingError("Each BGE embedding must have exactly 384 dimensions.")
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in values):
        raise EmbeddingError("BGE embedding values must be finite numbers.")
    try:
        vector = tuple(float(item) for item in values)
    except (OverflowError, TypeError, ValueError):
        raise EmbeddingError("BGE embedding values must be finite numbers.") from None
    if not all(math.isfinite(item) for item in vector):
        raise EmbeddingError("BGE embedding values must be finite numbers.")
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingError("BGE embeddings must have a finite non-zero norm.")
    # Guarantee unit length even if an injected backend ignores normalization.
    return tuple(item / norm for item in vector)
