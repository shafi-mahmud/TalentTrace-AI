"""Offline integration checks. SQL doubles do not prove PostgreSQL atomicity."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.services import submission_deletion as deletion
from app.services.candidate_inventory import Target


class JournalDatabase:
    def __init__(self, target, *, owned=True):
        self.owned = owned
        self.statements = []
        self.journal = dict(target.parameters(), plan_digest='a' * 64,
            file_digest='b' * 64, job_reference='TT-JOB-0123456789ABCDEF',
            file_type='pdf', state='file_pending')

    @asynccontextmanager
    async def context(self):
        yield self

    def begin(self):
        return self.context()

    async def scalar(self, query, params):
        sql = str(query)
        self.statements.append(sql)
        if sql.startswith('SELECT job_reference'):
            return self.journal['job_reference'] if self.owned else None
        return 0  # No residual associations in this synthetic SQL double.

    async def execute(self, query, params=None):
        sql = str(query)
        self.statements.append(sql)
        if sql.startswith('UPDATE submission_deletions'):
            self.journal['state'] = 'complete'
        return SimpleNamespace(mappings=lambda: SimpleNamespace(
            one_or_none=lambda: self.journal))


@pytest.fixture
def journal(tmp_path, monkeypatch):
    target = Target(uuid4(), uuid4(), uuid4(), uuid4())
    db = JournalDatabase(target)
    # Production maintenance boundary is NOT entered or weakened by these mocks.
    async def boundary(*args):
        pass
    monkeypatch.setattr(deletion, 'boundary', boundary)
    return target, db, tmp_path


def test_migration_is_unique_child_of_integrated_head():
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    cfg.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    scripts = ScriptDirectory.from_config(cfg)
    assert scripts.get_heads() == ['0016_submission_deletion']
    assert scripts.get_revision('head').down_revision == '0015_reviewer_confirmation'


def test_wrong_owner_stops_before_any_cleanup(journal):
    target, db, root = journal
    db.owned = False
    with pytest.raises(deletion.DeletionError, match='owned_job_not_found'):
        asyncio.run(deletion.delete_submission(db.context, target, root, 'a' * 64))
    assert not any(sql.startswith(('DELETE', 'UPDATE', 'INSERT')) for sql in db.statements)


def test_interrupted_retry_does_not_complete_or_remove_file(journal):
    target, db, root = journal
    path = deletion.exact_file(root, target, db.journal['job_reference'], 'pdf')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'synthetic only')
    def interrupt():
        raise RuntimeError('injected_after_commit')
    with pytest.raises(RuntimeError, match='injected_after_commit'):
        asyncio.run(deletion.delete_submission(db.context, target, root, 'a' * 64,
            after_commit=interrupt))
    assert db.journal['state'] == 'file_pending'
    assert path.read_bytes() == b'synthetic only'


def test_absent_file_retry_is_idempotent_without_new_deletes(journal):
    target, db, root = journal
    for _ in range(2):
        result = asyncio.run(deletion.delete_submission(db.context, target, root, 'a' * 64))
        assert result['state'] == 'complete' and result['maintenance'] == 'remains_closed'
    assert db.journal['state'] == 'complete'
    assert not any(sql.startswith(('DELETE', 'INSERT')) for sql in db.statements)


def test_changed_file_and_wrong_digest_refuse_retry(journal):
    target, db, root = journal
    path = deletion.exact_file(root, target, db.journal['job_reference'], 'pdf')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'changed synthetic file')
    with pytest.raises(deletion.DeletionError, match='file_integrity_changed'):
        asyncio.run(deletion.delete_submission(db.context, target, root, 'a' * 64))
    with pytest.raises(deletion.DeletionError, match='manifest_changed'):
        asyncio.run(deletion.delete_submission(db.context, target, root, 'c' * 64))
    assert path.exists() and db.journal['state'] == 'file_pending'


def test_import_replay_refused_before_reading_or_storing_cv(tmp_path, monkeypatch):
    from app.schemas.external_cv import ApprovedExternalSource
    from app.services import external_cv
    from test_external_cv_intake import Session, submission
    source = ApprovedExternalSource(source_id='synthetic_form', recruiter_id=uuid4(), job_id=uuid4())
    db = Session(source)
    async def suppressed(session, source_id, submission_id):
        assert session is db and source_id == source.source_id
        assert db.locked_reads == 1
        return True
    def forbidden(*args):
        pytest.fail('Deleted import must not fingerprint or store a CV')
    monkeypatch.setattr(deletion, 'import_suppressed', suppressed)
    monkeypatch.setattr(external_cv, 'fingerprint', forbidden)
    service = external_cv.ExternalCvImportService(lambda: db, tmp_path, (source,))
    with pytest.raises(external_cv.ExternalCvImportError) as error:
        asyncio.run(service.import_submission(submission()))
    assert error.value.code == 'submission_deleted'
    assert db.commits == 0 and not db.rows and not list(tmp_path.iterdir())


def test_normal_host_cannot_enter_destructive_boundary(tmp_path, monkeypatch):
    monkeypatch.delenv('N19_LAB_ID', raising=False)
    with pytest.raises(deletion.DeletionError, match='isolated_maintenance_required'):
        asyncio.run(deletion.boundary(None, tmp_path))
