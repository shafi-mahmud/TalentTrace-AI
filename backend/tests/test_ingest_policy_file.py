import asyncio
import os
import subprocess
import sys
from uuid import UUID, uuid4

import pytest

from app.rag import ingest_policy_file as cli
from app.rag.ingestion import CompanyPolicyIngestionError
from app.rag.policy_files import PolicyFileError


def options(path):
    return ["--file", str(path), "--title", "Synthetic External Policy", "--version", "2026-01"]


def test_metadata_generates_opaque_source_and_retains_supplied_identity(tmp_path):
    path = tmp_path / "private.txt"
    path.write_text("# Privacy\n\nProtect synthetic information.")
    source_id = uuid4()
    first = cli.load_policy_source(file=path, title="Synthetic Policy", version="v1", source_id=str(source_id))
    generated = cli.load_policy_source(file=path, title="Synthetic Policy", version="v1")
    assert first.source_id == source_id
    assert isinstance(generated.source_id, UUID)
    assert generated.source_id != source_id
    assert str(path) not in first.source_metadata().model_dump_json()


@pytest.mark.parametrize("field,value", [
    ("title", " "), ("title", "x" * 201), ("title", "Private\nTitle"),
    ("version", "private/path"), ("version", "x" * 65),
    ("source_id", "private-not-uuid"),
])
def test_metadata_validation_reuses_contract_before_reading(monkeypatch, field, value):
    monkeypatch.setattr(cli, "extract_policy_text", lambda _: pytest.fail("Invalid metadata must fail before extraction"))
    data = dict(file="private.txt", title="Synthetic Policy", version="v1")
    data[field] = value
    with pytest.raises(PolicyFileError, match="failed validation"):
        cli.load_policy_source(**data)


def test_unsafe_body_is_rejected_without_echo(tmp_path):
    path = tmp_path / "private.txt"
    path.write_text("PRIVATE_BODY\x00")
    with pytest.raises(PolicyFileError) as error:
        cli.load_policy_source(file=path, title="Safe title", version="v1")
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("duplicate", [False, True])
def test_delegates_to_existing_ingestion_and_disposes_engine(monkeypatch, tmp_path, duplicate):
    import app.db.session as db
    import app.rag.embeddings as embeddings
    import app.repositories.company_policy as repositories
    path = tmp_path / "policy.txt"
    path.write_text("Synthetic policy body")
    source = cli.load_policy_source(file=path, title="Synthetic Policy", version="v1")
    calls = []
    document_id = uuid4()
    class Engine:
        async def dispose(self):
            calls.append("disposed")
    engine, factory, embedding, expected_repository = Engine(), object(), object(), object()
    monkeypatch.setattr(db, "create_database_engine", lambda: engine)
    monkeypatch.setattr(db, "create_database_session_factory", lambda value: factory if value is engine else None)
    monkeypatch.setattr(embeddings, "BGEEmbeddingService", lambda: embedding)
    monkeypatch.setattr(repositories, "CompanyPolicyRepository", lambda value: expected_repository if value is factory else None)
    async def ingest(value, *, embedding_service, repository):
        assert value is source and embedding_service is embedding
        assert repository is expected_repository
        calls.append("existing_ingestion")
        if duplicate:
            raise CompanyPolicyIngestionError("Policy persistence failed: this source version or chunk identity already exists or conflicts with stored data.")
        return document_id
    monkeypatch.setattr(cli, "ingest_company_policy_source", ingest)
    if duplicate:
        with pytest.raises(CompanyPolicyIngestionError, match="already exists"):
            asyncio.run(cli.ingest_policy_file(source))
    else:
        assert asyncio.run(cli.ingest_policy_file(source)) == document_id
    assert calls == ["existing_ingestion", "disposed"]


def test_cli_safe_success_distinguishes_identities(tmp_path, monkeypatch, capsys):
    path = tmp_path / "private.txt"
    path.write_text("PRIVATE_SYNTHETIC_BODY")
    source_id, document_id = uuid4(), uuid4()
    async def ingest(source):
        assert source.source_id == source_id
        print("PRIVATE_MODEL_DIAGNOSTIC")
        return document_id
    monkeypatch.setattr(cli, "ingest_policy_file", ingest)
    assert cli.main(options(path) + ["--source-id", str(source_id)]) == 0
    output = capsys.readouterr()
    assert output.out == f"Policy ingestion succeeded.\nsource_id={source_id}\ndocument_id={document_id}\n"
    assert not output.err


@pytest.mark.parametrize("case", ["arguments", "metadata", "file", "unexpected", "database"])
def test_cli_failures_do_not_echo_private_values(tmp_path, monkeypatch, capsys, case):
    path = tmp_path / "PRIVATE_PATH.txt"
    path.write_text("PRIVATE_BODY")
    argv = options(path)
    if case == "arguments":
        argv += ["--PRIVATE_OPTION", "PRIVATE_SECRET"]
    elif case == "metadata":
        argv += ["--source-id", "PRIVATE_DATABASE_URL_PASSWORD"]
    elif case == "file":
        path.unlink()
    elif case == "database":
        import app.db.session as db
        def fail():
            raise RuntimeError("PRIVATE_DATABASE_URL_PASSWORD_SQL")
        monkeypatch.setattr(db, "create_database_engine", fail)
    else:
        async def fail(source):
            raise RuntimeError("PRIVATE_EMBEDDING_DATABASE_URL_PASSWORD")
        monkeypatch.setattr(cli, "ingest_policy_file", fail)
    assert cli.main(argv) == 1
    output = capsys.readouterr()
    assert output.out.startswith("Policy ingestion failed")
    assert "PRIVATE" not in output.out
    assert not output.err


def test_fresh_import_never_parses_files_connects_loads_models_or_ingests():
    code = '''
import pypdf, docx, asyncpg, sqlalchemy.ext.asyncio as db
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected initialization')
pypdf.PdfReader = forbidden
docx.Document = forbidden
asyncpg.connect = forbidden
db.create_async_engine = forbidden
import app.rag.policy_files as files
files.extract_policy_text = forbidden
import app.rag.ingestion as ingestion
ingestion.ingest_company_policy_source = forbidden
import app.rag.embeddings as embeddings
embeddings.BGEEmbeddingService._get_backend = forbidden
import app.rag.ingest_policy_file
from app.main import app
import sys
assert 'sentence_transformers' not in sys.modules
assert 'torch' not in sys.modules
assert app is not None
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, env=dict(os.environ))
    assert result.returncode == 0, "Import safety check failed; subprocess details withheld"
    assert not result.stdout and not result.stderr, "Unexpected import output; details withheld"
