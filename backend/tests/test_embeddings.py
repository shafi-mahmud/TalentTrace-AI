import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.rag.chunking import TokenCounter
from app.rag.embeddings import (
    BGE_EMBEDDING_DIMENSION,
    BGE_MODEL_NAME,
    BGE_QUERY_INSTRUCTION,
    BGEEmbeddingService,
    BGETokenCounter,
    EmbeddingError,
    EmbeddingService,
)


class FakeTokenizer:
    def __init__(self, ids: Any = None) -> None:
        self.ids = list(range(7)) if ids is None else ids
        self.calls: list[tuple[str, bool, bool]] = []

    def encode(self, text: str, *, add_special_tokens: bool, truncation: bool) -> Any:
        self.calls.append((text, add_special_tokens, truncation))
        return self.ids


class FakeBackend:
    def __init__(self, vectors: Any = None, tokenizer: FakeTokenizer | None = None) -> None:
        self.vectors = vectors
        self.tokenizer = tokenizer or FakeTokenizer()
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        self.calls.append((list(texts), kwargs))
        if self.vectors is not None:
            return self.vectors
        return [[1.0] * BGE_EMBEDDING_DIMENSION for _ in texts]


def test_documents_are_unprefixed_and_normalized() -> None:
    backend = FakeBackend()
    service: EmbeddingService = BGEEmbeddingService(backend_factory=lambda: backend)
    passages = ["Synthetic inclusive hiring policy.", "Synthetic security policy."]

    vectors = service.embed_documents(passages)

    assert backend.calls == [(passages, {
        "normalize_embeddings": True,
        "convert_to_numpy": True,
        "show_progress_bar": False,
        "prompt": "",
    })]
    assert len(vectors) == 2
    assert all(isinstance(vector, tuple) and len(vector) == 384 for vector in vectors)
    assert all(math.hypot(*vector) == pytest.approx(1.0) for vector in vectors)


def test_query_receives_the_exact_bge_instruction_once() -> None:
    backend = FakeBackend()
    service = BGEEmbeddingService(backend_factory=lambda: backend)

    vector = service.embed_query("Synthetic backend engineering skills")

    expected = BGE_QUERY_INSTRUCTION + "Synthetic backend engineering skills"
    assert backend.calls[0][0] == [expected]
    assert backend.calls[0][1]["prompt"] == ""
    assert backend.tokenizer.calls == [(expected, True, False)]
    assert len(vector) == 384
    assert math.hypot(*vector) == pytest.approx(1.0)


def test_batch_vectors_preserve_document_order() -> None:
    first = [1.0] + [0.0] * 383
    second = [0.0, 1.0] + [0.0] * 382
    backend = FakeBackend(vectors=[first, second])
    service = BGEEmbeddingService(backend_factory=lambda: backend)

    assert service.embed_documents(["First synthetic section", "Second synthetic section"]) == (
        tuple(first), tuple(second)
    )


@pytest.mark.parametrize("dimension", [0, 383, 385])
def test_wrong_dimensions_are_rejected(dimension: int) -> None:
    backend = FakeBackend(vectors=[[1.0] * dimension])
    service = BGEEmbeddingService(backend_factory=lambda: backend)

    with pytest.raises(EmbeddingError, match="exactly 384 dimensions"):
        service.embed_query("Synthetic query")


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), "1.0", None, True])
def test_nonfinite_and_nonnumeric_values_are_rejected(invalid: Any) -> None:
    backend = FakeBackend(vectors=[[invalid] + [1.0] * 383])
    service = BGEEmbeddingService(backend_factory=lambda: backend)

    with pytest.raises(EmbeddingError, match="finite numbers"):
        service.embed_query("Synthetic query")


def test_zero_vectors_are_rejected() -> None:
    service = BGEEmbeddingService(
        backend_factory=lambda: FakeBackend(vectors=[[0.0] * 384])
    )
    with pytest.raises(EmbeddingError, match="non-zero norm"):
        service.embed_query("Synthetic query")


@pytest.mark.parametrize("vectors", [[], [[1.0] * 384, [1.0] * 384]])
def test_unexpected_batch_size_is_rejected(vectors: Any) -> None:
    service = BGEEmbeddingService(backend_factory=lambda: FakeBackend(vectors=vectors))
    with pytest.raises(EmbeddingError, match="unexpected vector count"):
        service.embed_documents(["One synthetic passage"])


@pytest.mark.parametrize("vectors", [42, "private-marker", [42]])
def test_invalid_vector_structure_is_rejected(vectors: Any) -> None:
    service = BGEEmbeddingService(backend_factory=lambda: FakeBackend(vectors=vectors))
    with pytest.raises(EmbeddingError, match="invalid vector structure"):
        service.embed_query("Synthetic query")


@pytest.mark.parametrize("text", ["", " \n\t ", None, 42])
def test_empty_or_invalid_query_does_not_load_model(text: Any) -> None:
    def unexpected_load() -> Any:
        pytest.fail("Invalid input must not load the model.")

    with pytest.raises(EmbeddingError, match="non-empty text"):
        BGEEmbeddingService(backend_factory=unexpected_load).embed_query(text)


@pytest.mark.parametrize("texts", [[], [""], [" \n "], ["Valid passage", ""], "not a batch", None])
def test_empty_or_invalid_documents_do_not_load_model(texts: Any) -> None:
    def unexpected_load() -> Any:
        pytest.fail("Invalid input must not load the model.")

    with pytest.raises(EmbeddingError):
        BGEEmbeddingService(backend_factory=unexpected_load).embed_documents(texts)


def test_token_counter_uses_tokenizer_ids_and_reuses_the_lazy_backend() -> None:
    backend = FakeBackend()
    loads = []

    def load() -> FakeBackend:
        loads.append(True)
        return backend

    service = BGEEmbeddingService(backend_factory=load)
    counter: TokenCounter = BGETokenCounter(service)
    assert loads == []
    assert counter.count_tokens("two words") == 7
    assert backend.tokenizer.calls == [("two words", False, False)]
    service.embed_documents(["Synthetic passage"])
    service.embed_query("Synthetic query")
    assert len(loads) == 1


def test_token_counter_accepts_zero_tokens() -> None:
    backend = FakeBackend(tokenizer=FakeTokenizer(ids=[]))
    counter = BGETokenCounter(BGEEmbeddingService(backend_factory=lambda: backend))
    count = counter.count_tokens("")
    assert type(count) is int and count == 0


@pytest.mark.parametrize("ids", [-1, 1.5, True, "private-marker", [True], [-1], [1.5]])
def test_invalid_tokenizer_results_are_rejected(ids: Any) -> None:
    backend = FakeBackend(tokenizer=FakeTokenizer(ids=ids))
    counter = BGETokenCounter(BGEEmbeddingService(backend_factory=lambda: backend))
    with pytest.raises(EmbeddingError, match="invalid token IDs"):
        counter.count_tokens("Synthetic policy")


def test_overlong_text_is_rejected_before_encoding() -> None:
    backend = FakeBackend(tokenizer=FakeTokenizer(ids=list(range(513))))
    service = BGEEmbeddingService(backend_factory=lambda: backend)
    with pytest.raises(EmbeddingError, match="BGE token limit"):
        service.embed_documents(["Synthetic overlong passage"])
    assert backend.calls == []


def test_loader_options_disable_remote_code_and_credential_use(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    backend = FakeBackend()

    def fake_constructor(name: str, **kwargs: Any) -> FakeBackend:
        captured.update(model=name, **kwargs)
        return backend

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=fake_constructor))
    service = BGEEmbeddingService()
    assert captured == {}
    service.embed_query("Synthetic query")
    assert captured == {
        "model": BGE_MODEL_NAME,
        "device": "cpu",
        "trust_remote_code": False,
        "token": False,
        "model_kwargs": {"use_safetensors": True},
    }


@pytest.mark.parametrize("operation", ["load", "encode", "tokenize"])
def test_backend_failures_never_echo_text_or_internal_details(operation: str, capsys: pytest.CaptureFixture[str]) -> None:
    marker = "private-marker local-path credential-like-detail"
    backend = FakeBackend()

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(marker)

    if operation == "encode":
        backend.encode = fail
    if operation == "tokenize":
        backend.tokenizer.encode = fail
    service = BGEEmbeddingService(backend_factory=fail if operation == "load" else lambda: backend)
    with pytest.raises(EmbeddingError) as caught:
        service.embed_query(marker)
    assert marker not in str(caught.value)
    assert caught.value.__suppress_context__
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_application_import_and_adapter_construction_cannot_load_ml_or_use_network() -> None:
    # A fresh interpreter proves laziness even if another test imported the module.
    code = """
import importlib.abc
import socket
import sys
class BlockMLImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sentence_transformers', 'transformers', 'torch'}:
            raise AssertionError('ML import during application startup')
sys.meta_path.insert(0, BlockMLImports())
def block_network(*args, **kwargs):
    raise AssertionError('Network call during application startup')
socket.create_connection = block_network
socket.getaddrinfo = block_network
from app.rag.embeddings import BGEEmbeddingService, BGETokenCounter
service = BGEEmbeddingService()
counter = BGETokenCounter(service)
from app.main import app
assert app is not None
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, "Application import or lazy construction failed isolation checks."
