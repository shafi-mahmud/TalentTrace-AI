"""Synthetic internal-intake tests. No connector, provider or demo DB calls."""
import asyncio
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path
import os
import pytest
from pydantic import ValidationError
from starlette.datastructures import UploadFile, Headers
from app.schemas.external_cv import ApprovedExternalSource, ExternalCvSubmission
from app.services.external_cv import ExternalCvImportService, ExternalCvImportError
from app.services.cv_upload import CvUploadError
from test_cv_uploads import PDF, docx_bytes

REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9"


@pytest.fixture(autouse=True)
def no_external_provider_calls(monkeypatch):
    import httpx
    async def denied(*args,**kwargs):pytest.fail('Intake must not call external providers')
    monkeypatch.setattr(httpx.AsyncClient,'send',denied)


def submission(identifier="synthetic_001", data=PDF, kind="pdf", **changes):
    values=dict(source_id="synthetic_form", external_submission_id=identifier, job_reference=REFERENCE,
        synthetic=True, source_job_reference=REFERENCE, cv=UploadFile(BytesIO(data),filename=f"synthetic.{kind}",
        headers=Headers({"content-type":"application/pdf" if kind=="pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})))
    values.update(changes)
    return ExternalCvSubmission(**values)


class Session:
    def __init__(self, source, flush_error=False, commit_error=False, active=True):
        self.source=source;self.rows=[];self.active=active;self.flush_error=flush_error;self.commit_error=commit_error;self.commits=0;self.locked_reads=0
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def scalar(self,query):
        statement=str(query)
        if 'FROM job_profiles' in statement:
            self.locked_reads+=int(query._for_update_arg is not None)
            params=query.compile().params
            if self.source.job_id not in params.values() or self.source.recruiter_id not in params.values():return None
            return SimpleNamespace(id=self.source.job_id,job_reference=REFERENCE)
        if 'FROM recruiters' in statement:return self.active
        return next((r for r in self.rows if r.source_id in query.compile().params.values() and r.external_submission_id in query.compile().params.values()),None)
    def add(self,row):self.rows.append(row)
    async def flush(self):
        if self.flush_error:raise RuntimeError('private database detail')
    async def commit(self):
        self.commits+=1
        if self.commit_error:raise RuntimeError('private database detail')
    async def rollback(self):pass


@pytest.fixture
def source():return ApprovedExternalSource(source_id="synthetic_form",recruiter_id=uuid4(),job_id=uuid4())


@pytest.mark.parametrize('changes',[
    {'source_id':'../private'},{'source_id':'x'*65},{'external_submission_id':'x'*129},
    {'external_submission_id':'bad\0id'},{'synthetic':False},{'job_reference':'unknown'},
    {'candidate_email':'private@example.test'},{'api_key':'not-allowed'},{'cv':'/private/path.pdf'},
    {'recruiter_id':uuid4()},{'storage_root':'/private/path'}])
def test_contract_rejects_unsafe_or_unbounded_input(changes):
    with pytest.raises(ValidationError):submission(**changes)


@pytest.mark.parametrize('kind,data',[('pdf',PDF),('docx',docx_bytes())])
def test_import_reuses_native_storage_and_identical_retry(source,tmp_path,kind,data):
    async def run():
        session=Session(source);service=ExternalCvImportService(lambda:session,tmp_path,(source,))
        first=await service.import_submission(submission(data=data,kind=kind))
        second=await service.import_submission(submission(data=data,kind=kind))
        assert first.created and not second.created
        assert first.submission_id==second.submission_id and first.batch_id==second.batch_id
        assert first.status=='pending_review' and len(session.rows)==1 and session.commits==1 and session.locked_reads==2
        files=list(tmp_path.rglob(f'*.{kind}'));assert len(files)==1 and files[0].read_bytes()==data
        assert str(source.recruiter_id) in files[0].parts and REFERENCE in files[0].parts
    asyncio.run(run())


@pytest.mark.parametrize('case',['unknown_source','unknown_job','foreign_owner','wrong_reference','inactive'])
def test_source_job_and_owner_boundaries_do_not_write(source,tmp_path,case):
    async def run():
        session=Session(source,active=case!='inactive')
        binding=source
        if case=='foreign_owner':binding=source.model_copy(update={'recruiter_id':uuid4()})
        if case=='unknown_job':binding=source.model_copy(update={'job_id':uuid4()})
        service=ExternalCvImportService(lambda:session,tmp_path,(binding,))
        item=submission(source_id='unapproved' if case=='unknown_source' else source.source_id,
            job_reference='TT-JOB-AAAAAAAAAAAAAAAA' if case=='wrong_reference' else REFERENCE)
        with pytest.raises(ExternalCvImportError) as error:await service.import_submission(item)
        assert error.value.code in ['source_not_approved','job_not_available']
        assert not list(tmp_path.iterdir()) and not session.rows
    asyncio.run(run())


def test_conflicting_duplicate_and_missing_previous_file_are_not_reimported(source,tmp_path):
    async def run():
        session=Session(source);service=ExternalCvImportService(lambda:session,tmp_path,(source,))
        first=await service.import_submission(submission())
        with pytest.raises(ExternalCvImportError,match='different input'):await service.import_submission(submission(data=PDF+b'\n'))
        assert len(session.rows)==1 and len(list(tmp_path.rglob('*.pdf')))==1
        list(tmp_path.rglob('*.pdf'))[0].unlink()
        with pytest.raises(ExternalCvImportError) as error:await service.import_submission(submission())
        assert error.value.code=='stored_submission_unavailable' and len(session.rows)==1
    asyncio.run(run())


@pytest.mark.parametrize('kind,data',[('pdf',b'not a pdf'),('docx',docx_bytes(('word/embeddings/unsafe.bin','synthetic')))])
def test_invalid_files_use_native_rejection_and_cleanup(source,tmp_path,kind,data):
    async def run():
        session=Session(source);service=ExternalCvImportService(lambda:session,tmp_path,(source,))
        with pytest.raises(CvUploadError):await service.import_submission(submission(kind=kind,data=data))
        assert not session.rows and not list(tmp_path.rglob(f'*.{kind}'))
    asyncio.run(run())


@pytest.mark.parametrize('phase',['flush','commit'])
def test_database_failure_cleanup_and_uncertain_commit_are_distinct(source,tmp_path,phase):
    async def run():
        session=Session(source,flush_error=phase=='flush',commit_error=phase=='commit')
        service=ExternalCvImportService(lambda:session,tmp_path,(source,))
        with pytest.raises(ExternalCvImportError) as error:await service.import_submission(submission())
        assert 'private' not in str(error.value)
        assert error.value.code==('confirmation_unknown' if phase=='commit' else 'import_failed')
        assert len(list(tmp_path.rglob('*.pdf')))==(1 if phase=='commit' else 0)
        if phase=='commit':
            session.commit_error=False
            retry=await service.import_submission(submission());assert not retry.created and len(session.rows)==1
    asyncio.run(run())


def test_native_write_failure_never_creates_a_record(source,tmp_path,monkeypatch):
    original=Path.open
    def failure(path,*args,**kwargs):
        if args and args[0]=='xb':raise OSError('private filesystem detail')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',failure)
    async def run():
        session=Session(source);service=ExternalCvImportService(lambda:session,tmp_path,(source,))
        with pytest.raises(CvUploadError) as error:await service.import_submission(submission())
        assert error.value.code=='storage_failed' and not session.rows
        assert not list(tmp_path.rglob('*.pdf'))
    asyncio.run(run())


def test_duplicate_approval_is_rejected(source,tmp_path):
    with pytest.raises(ValueError):ExternalCvImportService(None,tmp_path,(source,source))


def test_ledger_migration_offline_sql_and_constraints():
    from alembic import command
    from alembic.config import Config
    from io import StringIO
    output=StringIO();configuration=Config('alembic.ini',output_buffer=output)
    command.upgrade(configuration,'0007_interview_email:head',sql=True)
    sql=output.getvalue()
    for fragment in ['CREATE TABLE external_cv_submissions','uq_external_cv_submission',
        'FOREIGN KEY(job_id) REFERENCES job_profiles','ck_external_cv_status']:
        assert fragment in sql
    assert 'CREATE TABLE candidate' not in sql and 'CREATE TABLE recruiter' not in sql


def test_real_postgres_concurrent_retry_and_ownership(tmp_path):
    """Explicit disposable URL only; never selects DATABASE_URL or local .env."""
    url=os.environ.get('EXTERNAL_INTAKE_TEST_DATABASE_URL')
    if not url:pytest.skip('Disposable PostgreSQL not configured')
    from urllib.parse import urlsplit
    assert urlsplit(url).path=='/talenttrace_external_intake_test'
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from sqlalchemy import select,func
    from app.db.models.recruiter import Recruiter,JobProfile
    from app.db.models.external_cv import ExternalCvSubmissionRecord
    async def run():
        engine=create_async_engine(url,hide_parameters=True);factory=async_sessionmaker(engine,expire_on_commit=False)
        owner,foreign,job_id=uuid4(),uuid4(),uuid4()
        reference='TT-JOB-'+job_id.hex[:16].upper()
        source=ApprovedExternalSource(source_id='synthetic_form_'+owner.hex[:8],recruiter_id=owner,job_id=job_id)
        try:
            async with factory() as s:
                s.add_all([Recruiter(id=owner,email=owner.hex+'@example.test',password_hash='synthetic-not-a-login',active=True),Recruiter(id=foreign,email=foreign.hex+'@example.test',password_hash='synthetic-not-a-login',active=True)])
                await s.flush()
                s.add(JobProfile(id=job_id,recruiter_id=owner,job_reference=reference,job_title='Synthetic intake job',suggestions={},sources=[],revision=1))
                await s.commit()
            service=ExternalCvImportService(factory,tmp_path,(source,))
            values=await asyncio.gather(*(service.import_submission(submission(source_id=source.source_id,job_reference=reference)) for _ in range(3)))
            assert sum(v.created for v in values)==1 and len({v.submission_id for v in values})==1
            async with factory() as s:
                assert await s.scalar(select(func.count()).select_from(ExternalCvSubmissionRecord).where(ExternalCvSubmissionRecord.job_id==job_id))==1
            assert len(list(tmp_path.rglob('*.pdf')))==1
            denied=ExternalCvImportService(factory,tmp_path,(source.model_copy(update={'recruiter_id':foreign}),))
            with pytest.raises(ExternalCvImportError):await denied.import_submission(submission(identifier='synthetic_002',source_id=source.source_id,job_reference=reference))
            doc=await service.import_submission(submission(identifier='synthetic_docx',source_id=source.source_id,job_reference=reference,kind='docx',data=docx_bytes()))
            assert doc.created and doc.file.file_type=='docx'
            async with factory() as s:
                row=await s.get(ExternalCvSubmissionRecord,doc.submission_id)
                assert row.status=='pending_review' and row.job_id==job_id and row.upload_id==doc.file.upload_id
        finally:await engine.dispose()
    asyncio.run(run())
