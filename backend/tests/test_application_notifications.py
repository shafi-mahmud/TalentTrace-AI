import asyncio
from datetime import datetime, timedelta, timezone
from io import StringIO
import os
import secrets
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.auth import database_session, token_hash
from app.db.models.application_view import ApplicationView
from app.db.models.external_cv import ExternalCvSubmissionRecord as Submission
from app.db.models.recruiter import Recruiter, RecruiterSession, JobProfile, CandidateScoreRecord
from app.main import app
from app.api.routers import application_notifications as route
from app.services.application_notifications import stored_applications, reconcile, mark_viewed


def stored(root, reference, *, batch=None, upload=None, content=b"%PDF-1.7\nsynthetic\n%%EOF"):
    batch, upload = batch or uuid4(), upload or uuid4()
    directory = root / reference / str(batch)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{upload}.pdf").write_bytes(content)
    return batch, upload


@pytest.mark.parametrize("count", [0,1,4])
def test_zero_single_multiple_native_files(tmp_path, count):
    ref="TT-JOB-"+"A"*16
    for _ in range(count): stored(tmp_path,ref)
    files, invalid = stored_applications(tmp_path,ref)
    items=reconcile(files,[],set())
    assert len(items)==count and invalid==0
    assert all(row['is_new'] for row in items)


def test_ledger_and_file_deduplicated_missing_is_explicit(tmp_path):
    ref="TT-JOB-"+"A"*16
    key=stored(tmp_path,ref)
    files,_=stored_applications(tmp_path,ref)
    row=N(batch_id=key[0],upload_id=key[1],file_type='pdf',size_bytes=files[key][1])
    assert len(reconcile(files,[row],set()))==1
    items=reconcile({},[row],{key})
    assert items[0]['available'] is False and items[0]['is_new'] is False


def test_invalid_cv_excluded_and_other_job_not_counted(tmp_path):
    ref="TT-JOB-"+"A"*16
    stored(tmp_path,ref,content=b'not a pdf')
    stored(tmp_path,"TT-JOB-"+"B"*16)
    files,invalid=stored_applications(tmp_path,ref)
    assert files=={} and invalid==1


def test_new_is_unviewed_not_unscreened():
    old,new=(uuid4(),uuid4()),(uuid4(),uuid4())
    items=reconcile({old:('pdf',20),new:('pdf',20)},[],{old})
    assert sum(r['is_new'] for r in items)==1


def test_limit_is_explicit_not_a_partial_count(monkeypatch,tmp_path):
    import app.services.application_notifications as service
    monkeypatch.setattr(service,'MAX_APPLICATIONS',1)
    ref='TT-JOB-'+'A'*16
    stored(tmp_path,ref);stored(tmp_path,ref)
    with pytest.raises(HTTPException) as failure:stored_applications(tmp_path,ref)
    assert failure.value.status_code==409


def test_unsafe_storage_cannot_be_reported_as_zero(monkeypatch,tmp_path):
    root=tmp_path/'storage';root.write_text('synthetic',encoding='utf-8')
    with pytest.raises(HTTPException):stored_applications(root,'TT-JOB-'+'A'*16)
    monkeypatch.setattr(Path,'is_junction',lambda path:path==tmp_path)
    with pytest.raises(HTTPException):stored_applications(tmp_path,'TT-JOB-'+'A'*16)


def test_unknown_acknowledgement_never_writes(monkeypatch):
    async def discover(*args):return {'applications':[]}
    monkeypatch.setattr('app.services.application_notifications.discover',discover)
    class NoWrites:
        async def execute(self,*args):pytest.fail('No writes allowed')
    with pytest.raises(HTTPException):
        asyncio.run(mark_viewed(NoWrites(),N(id=uuid4()),Path('unused'),[N(batch_id=uuid4(),upload_id=uuid4())]))


@pytest.fixture(scope='module')
def notification_pg():
    if os.environ.get('NOTIFICATIONS_PG_TEST') != '1':
        pytest.skip('Enable explicit disposable PostgreSQL notification tests')
    port=54403
    with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    container='talenttrace-notification-test-'+uuid4().hex[:10]
    image=subprocess.run(['docker','inspect','--format','{{.Config.Image}}','talenttrace-f4-local-20261012'],capture_output=True,text=True,check=True).stdout.strip()
    password=secrets.token_urlsafe(32)
    result=subprocess.run(['docker','run','--pull=never','--rm','-d','--name',container,
        '-p',f'127.0.0.1:{port}:5432','-e','POSTGRES_USER=notification_test','-e','POSTGRES_DB=notification_test',
        '-e','POSTGRES_PASSWORD='+password,image],capture_output=True,text=True)
    assert result.returncode==0,'Disposable PostgreSQL could not start'
    url=URL.create('postgresql+asyncpg',username='notification_test',password=password,
        host='127.0.0.1',port=port,database='notification_test')
    async def ready():
        engine=create_async_engine(url,echo=False,hide_parameters=True)
        try:
            for _ in range(100):
                try:
                    async with engine.connect() as connection:await connection.execute(text('SELECT 1'))
                    return
                except Exception:await asyncio.sleep(.2)
            pytest.fail('Disposable PostgreSQL TCP not ready')
        finally:await engine.dispose()
    def sql(value):
        result=subprocess.run(['docker','exec','-i',container,'psql','-v','ON_ERROR_STOP=1','-U','notification_test','-d','notification_test'],input=value,text=True,capture_output=True)
        assert result.returncode==0,'Disposable SQL verification failed'
        return result.stdout
    def migration(target,down=False):
        output=StringIO();cfg=Config(str(Path(__file__).parents[1]/'alembic.ini'),output_buffer=output)
        (command.downgrade if down else command.upgrade)(cfg,target,sql=True)
        sql(output.getvalue())
    try:
        asyncio.run(ready())
        migration('0011_application_views')
        sentinel=uuid4()
        sql(f"INSERT INTO recruiters(id,email,password_hash,active) VALUES ('{sentinel}','sentinel@example.test','unused',true);")
        migration('0011_application_views:0010_interview_transcripts',down=True)
        migration('0010_interview_transcripts:0011_application_views')
        assert '1' in sql(f"SELECT count(*) FROM recruiters WHERE id='{sentinel}';")
        assert '0011_application_views' in sql('SELECT version_num FROM alembic_version;')
        yield url
    finally:
        subprocess.run(['docker','stop',container],capture_output=True,check=True)


def test_real_postgres_authenticated_counts_acknowledgement_and_isolation(notification_pg,tmp_path,monkeypatch):
    async def run():
        assert notification_pg.port==54403 and notification_pg.database=='notification_test'
        engine=create_async_engine(notification_pg,echo=False,hide_parameters=True)
        sessions=async_sessionmaker(engine,expire_on_commit=False)
        owner,other,job,other_job=uuid4(),uuid4(),uuid4(),uuid4()
        token='a'*43; other_token='b'*43
        ref='TT-JOB-'+job.hex[:16].upper()
        root=tmp_path / 'uploads'
        async with sessions.begin() as db:
            for identity,t in [(owner,token),(other,other_token)]:
                db.add(Recruiter(id=identity,email=f'{identity}@example.test',password_hash='unused',active=True));await db.flush()
                db.add(RecruiterSession(token_hash=token_hash(t),recruiter_id=identity,expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
            for identity,o in [(job,owner),(other_job,other)]:
                db.add(JobProfile(id=identity,recruiter_id=o,job_reference=ref if identity==job else 'TT-JOB-'+identity.hex[:16].upper(),job_title='Synthetic',revision=1,suggestions={},sources=[],scoring_weights={'skill':100,'education':0,'experience':0}))
        async def database():
            async with sessions() as db:yield db
        previous=dict(app.dependency_overrides)
        app.dependency_overrides[database_session]=database
        monkeypatch.setattr(route,'private_settings',lambda request:N(cv_upload_root=root/str(request.state.recruiter_id)))
        path=f'/api/v1/jobs/{job}/applications'
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',cookies={'talenttrace_session':token},headers={'X-TalentTrace-Request':'1'}) as client:
                response=await client.get(path)
                assert response.status_code==200 and response.json()['received_count']==0
                first=stored(root/str(owner),ref)
                one=(await client.get(path)).json();assert one['received_count']==one['new_count']==1
                async with sessions.begin() as db:
                    db.add(CandidateScoreRecord(id=uuid4(),job_id=job,batch_id=first[0],upload_id=first[1],criteria_revision=1,scoring_version='synthetic',score=100,payload={'synthetic':True}))
                # Simulates a trusted ledger referencing the SAME stored file.
                async with sessions.begin() as db:
                    db.add(Submission(id=uuid4(),job_id=job,source_job_reference=ref,source_id='synthetic',external_submission_id='synthetic-1',batch_id=first[0],upload_id=first[1],file_type='pdf',size_bytes=30,content_sha256='a'*64,status='pending_review'))
                # Native fixture length is read from persisted bytes, not guessed.
                async with sessions.begin() as db:
                    row=await db.scalar(select(Submission).where(Submission.job_id==job));row.size_bytes=(root/str(owner)/ref/str(first[0])/f'{first[1]}.pdf').stat().st_size
                one=(await client.get(path)).json();assert one['received_count']==1 and one['unavailable_count']==0
                assert 'email' not in str(one) and 'synthetic-1' not in str(one)
                assert (await client.post(path+'/viewed',json={'applications':one['applications']})).status_code==422
                ids=[{k:r[k] for k in ('batch_id','upload_id')} for r in one['applications']]
                for _ in range(2):assert (await client.post(path+'/viewed',json={'applications':ids})).status_code==204
                assert (await client.get(path)).json()['new_count']==0
                second=stored(root/str(owner),ref)
                two=(await client.get(path)).json();assert two['received_count']==2 and two['new_count']==1
                # Acknowledging an OLD displayed list must not clear a later arrival.
                assert (await client.post(path+'/viewed',json={'applications':ids})).status_code==204
                assert (await client.get(path)).json()['new_count']==1
                foreign=f'/api/v1/jobs/{other_job}/applications'
                assert (await client.get(foreign)).status_code==404
                assert (await client.post(foreign+'/viewed',json={'applications':[]})).status_code==404
                assert (await client.post(path+'/viewed',json={'applications':[{'batch_id':str(uuid4()),'upload_id':str(uuid4())}]})).status_code==409
                # Missing imported PDF remains received but unavailable; native invalid is excluded.
                (root/str(owner)/ref/str(first[0])/f'{first[1]}.pdf').unlink()
                stored(root/str(owner),ref,content=b'invalid')
                state=(await client.get(path)).json()
                assert state['received_count']==2 and state['unavailable_count']==1 and state['invalid_batch_count']==2
                assert (await client.post(path+'/viewed',json={'applications':ids},headers={'X-TalentTrace-Request':'0'})).status_code==403
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as anon:
                assert (await anon.get(path)).status_code==401
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',cookies={'talenttrace_session':other_token}) as foreign:
                assert (await foreign.get(path)).status_code==404
                own=(await foreign.get(f'/api/v1/jobs/{other_job}/applications')).json()
                assert own['received_count']==own['new_count']==0
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(ApplicationView).where(ApplicationView.job_id==job))==1
                scores=(await db.scalars(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id==job))).all()
                assert len(scores)==1 and scores[0].score==100 and scores[0].payload=={'synthetic':True}
                assert await db.scalar(select(func.count()).select_from(Submission).where(Submission.job_id==job))==1
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(previous)
            await engine.dispose()
    asyncio.run(run())
