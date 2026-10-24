"""Opt-in NEW disposable PostgreSQL; never accept an existing database URL."""
import asyncio, json, os, secrets, subprocess, time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text, select, func
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.recruiter import Recruiter, InterviewInvitation, InterviewSchedule, BookedInterviewEmailAttempt
from app.api.routers.booked_interview_email import send_reviewed, SendRequest, status
from app.services import booked_interview_email as delivery
from test_booked_interview_email import records
from test_interview_email import config

@pytest.fixture(scope='module')
def disposable_pg():
    if os.getenv('BOOKED_EMAIL_PG_TEST')!='1':pytest.skip('Explicit disposable PostgreSQL opt-in required')
    image='pgvector/pgvector:0.8.6-pg17-bookworm'
    assert subprocess.run(['docker','image','inspect',image],capture_output=True).returncode==0,'Local image unavailable'
    name='tt-booked-email-test-'+uuid4().hex[:12];password=secrets.token_urlsafe(32)
    result=subprocess.run(['docker','run','--pull=never','--rm','-d','--name',name,'--label','talenttrace.test-only=booked-email',
        '-p','127.0.0.1::5432','-e','POSTGRES_USER=booked_email_test','-e','POSTGRES_DB=booked_email_test',
        '-e','POSTGRES_PASSWORD='+password,image],capture_output=True,text=True)
    assert result.returncode==0,'New disposable database could not start'
    try:
        info=json.loads(subprocess.run(['docker','inspect',name],capture_output=True,text=True,check=True).stdout)[0]
        assert info['Config']['Labels']['talenttrace.test-only']=='booked-email'
        assert all(m['Type']=='volume' for m in info['Mounts'])
        assert not info['HostConfig']['Binds'] and not info['HostConfig']['VolumesFrom']
        binding=info['NetworkSettings']['Ports']['5432/tcp'];assert len(binding)==1 and binding[0]['HostIp']=='127.0.0.1'
        for _ in range(100):
            if subprocess.run(['docker','exec',name,'pg_isready','-U','booked_email_test'],capture_output=True).returncode==0:break
            time.sleep(.2)
        else:pytest.fail('Disposable database readiness timeout')
        output=StringIO();cfg=Config(str(Path(__file__).parents[1]/'alembic.ini'),output_buffer=output)
        cfg.set_main_option('script_location',str(Path(__file__).parents[1]/'alembic'));command.upgrade(cfg,'head',sql=True)
        migrated=subprocess.run(['docker','exec','-i',name,'psql','-v','ON_ERROR_STOP=1','-U','booked_email_test','-d','booked_email_test'],input=output.getvalue(),capture_output=True,text=True)
        assert migrated.returncode==0,'Fresh schema migration failed'
        yield URL.create('postgresql+asyncpg',username='booked_email_test',password=password,host='127.0.0.1',port=int(binding[0]['HostPort']),database='booked_email_test')
    finally:subprocess.run(['docker','stop','--time','10',name],capture_output=True,check=True)


def test_postgres_concurrent_reservation_and_interrupted_send(disposable_pg,monkeypatch):
    async def run():
        engine=create_async_engine(disposable_pg,echo=False,hide_parameters=True);sessions=async_sessionmaker(engine,expire_on_commit=False)
        try:
            owner=uuid4();job,row=records(owner);invitation_id=uuid4()
            async with sessions.begin() as db:
                assert await db.scalar(text('SELECT version_num FROM alembic_version'))=='0017_booked_interview_email'
                db.add(Recruiter(id=owner,email='owner@example.test',password_hash='unused',active=True));await db.flush()
                db.add(job);await db.flush();db.add(row);await db.flush()
                db.add(InterviewInvitation(id=invitation_id,interview_id=row.id,token_hash='b'*64,expires_at=row.scheduled_at,revoked=False,candidate_session_hash=None))
            c=config();to='approved@synthetic.invalid';user=N(id=owner)
            body=SendRequest(recipient=to,review_digest=delivery.preview(job,row,to)['review_digest'],confirmed=True)
            entered=asyncio.Event();release=asyncio.Event()
            class Transport:
                calls=0
                def send(self,*args):self.calls+=1
            transport=Transport();original=delivery.dispatch
            async def held(*args):
                async with sessions() as observed:assert (await observed.get(BookedInterviewEmailAttempt,row.id)).status=='sending'
                entered.set();await release.wait();return await original(*args)
            monkeypatch.setattr(delivery,'dispatch',held)
            async with sessions() as first,sessions() as second:
                sending=asyncio.create_task(send_reviewed(job.id,row.id,body,user,first,configuration=c,transport=transport))
                await asyncio.wait_for(entered.wait(),10)
                assert await send_reviewed(job.id,row.id,body,user,second,configuration=c,transport=transport)=={'email_status':'uncertain'}
                assert transport.calls==0;release.set();assert await sending=={'email_status':'accepted'}
            monkeypatch.setattr(delivery,'dispatch',original)
            assert transport.calls==1
            async with sessions() as db:
                assert (await db.get(BookedInterviewEmailAttempt,row.id)).status=='accepted'
                inv=await db.get(InterviewInvitation,invitation_id)
                assert inv.token_hash=='b'*64 and inv.candidate_session_hash is None and inv.revoked is False
                assert await db.scalar(select(func.count()).select_from(BookedInterviewEmailAttempt))==1
            interrupted=InterviewSchedule(id=uuid4(),recruiter_id=owner,job_id=job.id,batch_id=uuid4(),upload_id=uuid4(),criteria_revision=2,
                scoring_version=row.scoring_version,scheduled_at=row.scheduled_at,timezone=row.timezone,duration_minutes=30,unscored_confirmed=False,screening_snapshot=row.screening_snapshot)
            async with sessions.begin() as db:db.add(interrupted)
            body2=SendRequest(recipient=to,review_digest=delivery.preview(job,interrupted,to)['review_digest'],confirmed=True)
            async def cancelled(*args):raise asyncio.CancelledError()
            monkeypatch.setattr(delivery,'dispatch',cancelled)
            async with sessions() as db:
                with pytest.raises(asyncio.CancelledError):await send_reviewed(job.id,interrupted.id,body2,user,db,configuration=c,transport=transport)
            monkeypatch.setattr(delivery,'dispatch',original)
            async with sessions() as db:
                attempt=await db.get(BookedInterviewEmailAttempt,interrupted.id)
                assert attempt.status=='sending' and status(attempt)=='uncertain'
                assert await send_reviewed(job.id,interrupted.id,body2,user,db,configuration=c,transport=transport)=={'email_status':'uncertain'}
            assert transport.calls==1
        finally:await engine.dispose()
    asyncio.run(run())
