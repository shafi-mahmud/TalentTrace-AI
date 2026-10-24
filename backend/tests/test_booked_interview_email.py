"""Synthetic auth/API and transport acceptance; SQL double unless explicitly opted in."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from fastapi import HTTPException
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from io import StringIO
from app.api.routers import booked_interview_email as route
from app.services import booked_interview_email as delivery
from app.db.models.recruiter import JobProfile, InterviewSchedule, InterviewInvitation, BookedInterviewEmailAttempt, SchedulingInvitation
from test_interview_email import config, Fake
from test_recruiter_records import workspace, client, login, TABLES, SessionDouble


def records(owner):
    job=JobProfile(id=uuid4(), recruiter_id=owner, job_reference='TT-JOB-0123456789ABCDEF', job_title='Synthetic',
        revision=2, sources=[], suggestions={}, confirmed_snapshot={'criteria':[]}, scoring_weights={'skill':100,'education':0,'experience':0})
    row=InterviewSchedule(id=uuid4(),recruiter_id=owner,job_id=job.id,batch_id=uuid4(),upload_id=uuid4(),
        criteria_revision=2,scoring_version='f2-coverage-v1',scheduled_at=datetime(2099,11,20,9,tzinfo=timezone.utc),
        timezone='Asia/Dhaka',duration_minutes=60,unscored_confirmed=False,screening_snapshot={'screening_decision':'eligible'})
    return job,row


@pytest.fixture
def booked(workspace,monkeypatch):
    db,users,password=workspace
    job,row=records(users[0].id)
    invitation=InterviewInvitation(id=uuid4(),interview_id=row.id,token_hash='a'*64,expires_at=row.scheduled_at,revoked=False,candidate_session_hash=None)
    db.update({JobProfile:[job],InterviewSchedule:[row],InterviewInvitation:[invitation],BookedInterviewEmailAttempt:[],SchedulingInvitation:[]})
    for model in (InterviewSchedule,InterviewInvitation,BookedInterviewEmailAttempt,SchedulingInvitation):monkeypatch.setitem(TABLES,model.__tablename__,model)
    c=config();c.livekit_synthetic_demo_enabled=False;c.interview_public_origin=None
    monkeypatch.setattr(route,'settings',c)
    return db,users,password,job,row,c


def test_review_auth_saved_data_allowlist_staleness_and_invitation_preserved(booked,monkeypatch):
    db,users,password,job,row,c=booked
    before=deepcopy(db[InterviewInvitation][0].__dict__)
    calls=[]
    async def fake(configuration,to,subject,body,transport=None):
        assert db[BookedInterviewEmailAttempt][0].status=='sending'  # reservation already committed
        calls.append(body);return 'accepted'
    monkeypatch.setattr(delivery,'dispatch',fake)
    path=f'/api/v1/jobs/{job.id}/interviews/{row.id}/appointment-email'
    async def run():
        async with client() as owner,client() as foreign,client() as anon:
            assert (await anon.get(path)).status_code==401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            assert (await foreign.get(path)).status_code==404
            assert (await foreign.post(path+'/preview',json={'recipient':'approved@synthetic.invalid'})).status_code==404
            assert (await owner.post(path.replace(str(row.id),str(uuid4()))+'/preview',json={'recipient':'approved@synthetic.invalid'})).status_code==404
            assert (await owner.get(path)).json()=={'email_status':'none'}
            assert (await owner.get(path.replace(str(job.id),str(uuid4())))).status_code==404
            assert (await owner.post(path+'/preview',json={'recipient':'other@synthetic.invalid'})).status_code==422
            request={'recipient':'approved@synthetic.invalid'}
            r=await owner.post(path+'/preview',json=request);assert r.status_code==200
            value=r.json();assert set(value)=={'subject','body','review_digest'}
            assert '15:00' in value['body'] and '16:00' in value['body'] and 'Asia/Dhaka' in value['body']
            assert str(row.upload_id) in value['body'] and job.job_reference in value['body']
            assert '/interview-join' not in value['body'] and 'no joining link' in value['body']
            assert 'approved@synthetic.invalid' not in r.text and 'a'*64 not in r.text
            payload={**request,'review_digest':value['review_digest'],'confirmed':True}
            assert (await owner.post(path,json={**payload,'confirmed':1})).status_code==422
            db[JobProfile][0].revision=3
            assert (await owner.post(path,json=payload)).status_code==409
            db[JobProfile][0].revision=2
            db[InterviewSchedule][0].duration_minutes=30
            assert (await owner.post(path,json=payload)).status_code==409
            db[InterviewSchedule][0].duration_minutes=60
            assert (await owner.post(path,json=payload)).json()=={'email_status':'accepted'}
            assert (await owner.post(path,json=payload)).json()=={'email_status':'accepted'}
            assert len(calls)==1
            assert (await owner.get(path)).json()=={'email_status':'accepted'}
            assert (await foreign.post(path,json=payload)).status_code==404
    asyncio.run(run())
    for key,value in before.items():
        if key!='_sa_instance_state':assert getattr(db[InterviewInvitation][0],key)==value
    assert len(db[InterviewInvitation])==1
    assert set(BookedInterviewEmailAttempt.__table__.columns.keys())=={'interview_id','status','created_at'}


@pytest.mark.parametrize('status',['sending','uncertain','failed','accepted'])
def test_persisted_attempt_never_resends_even_after_reload(booked,status):
    db,users,_,job,row,c=booked
    db[BookedInterviewEmailAttempt]=[BookedInterviewEmailAttempt(interview_id=row.id,status=status)]
    fake=Fake()
    body=route.SendRequest(recipient='approved@synthetic.invalid',review_digest='0'*64,confirmed=True)
    result=asyncio.run(route.send_reviewed(job.id,row.id,body,users[0],SessionDouble(db),configuration=c,transport=fake))
    assert result=={'email_status':'uncertain' if status=='sending' else status} and not fake.messages


@pytest.mark.parametrize('error,expected',[(None,'accepted'),(TimeoutError('PRIVATE'),'uncertain'),(OSError('PRIVATE'),'uncertain')])
def test_transport_outcomes_are_sanitized(error,expected,capsys):
    assert asyncio.run(delivery.dispatch(config(),'approved@synthetic.invalid','Synthetic','Synthetic',Fake(error)))==expected
    assert 'PRIVATE' not in capsys.readouterr().out


def test_failed_transport_and_commit_failure_no_retry(booked,monkeypatch):
    import smtplib
    db,users,_,job,row,c=booked
    body=route.SendRequest(recipient='approved@synthetic.invalid',review_digest=delivery.preview(job,row,'approved@synthetic.invalid')['review_digest'],confirmed=True)
    fake=Fake(smtplib.SMTPRecipientsRefused({}))
    assert asyncio.run(route.send_reviewed(job.id,row.id,body,users[0],SessionDouble(db),configuration=c,transport=fake))=={'email_status':'failed'}
    db[BookedInterviewEmailAttempt]=[]
    class Broken(SessionDouble):
        commits=0
        async def commit(self):
            self.commits+=1
            if self.commits==2:raise RuntimeError('PRIVATE')
            await super().commit()
        async def rollback(self):pass
    assert asyncio.run(route.send_reviewed(job.id,row.id,body,users[0],Broken(db),configuration=c,transport=Fake()))=={'email_status':'uncertain'}
    assert db[BookedInterviewEmailAttempt][0].status=='sending'


def test_not_configured_past_or_self_scheduled_fails_without_attempt(booked):
    db,users,_,job,row,c=booked
    payload=route.SendRequest(recipient='approved@synthetic.invalid',review_digest='0'*64,confirmed=True)
    c.interview_email_enabled=False
    with pytest.raises(HTTPException) as e:asyncio.run(route.send_reviewed(job.id,row.id,payload,users[0],SessionDouble(db),configuration=c,transport=Fake()))
    assert e.value.status_code==503 and not db[BookedInterviewEmailAttempt]
    c.interview_email_enabled=True;db[InterviewSchedule][0].scheduled_at=datetime(2020,1,1,tzinfo=timezone.utc)
    with pytest.raises(HTTPException) as e:asyncio.run(route.send_reviewed(job.id,row.id,payload,users[0],SessionDouble(db),configuration=c,transport=Fake()))
    assert e.value.status_code==409
    db[SchedulingInvitation]=[SchedulingInvitation(interview_id=row.id)]
    with pytest.raises(HTTPException) as e:asyncio.run(route.send_reviewed(job.id,row.id,payload,users[0],SessionDouble(db),configuration=c,transport=Fake()))
    assert e.value.status_code==409 and not db[BookedInterviewEmailAttempt]


def test_preview_digest_binds_recipient_and_full_saved_schedule():
    job,row=records(uuid4());first=delivery.preview(job,row,'approved@synthetic.invalid')
    assert first['review_digest']!=delivery.preview(job,row,'other@synthetic.invalid')['review_digest']
    row.timezone='America/New_York';assert first['review_digest']!=delivery.preview(job,row,'approved@synthetic.invalid')['review_digest']
    # Crossing a DST fallback still represents actual elapsed duration.
    row.scheduled_at=datetime(2099,11,1,5,30,tzinfo=timezone.utc);row.duration_minutes=120
    assert 'Duration: 120 minutes' in delivery.preview(job,row,'approved@synthetic.invalid')['body']


def test_migration_has_single_head_unique_reservation_and_safe_downgrade():
    cfg=Config('alembic.ini');scripts=ScriptDirectory.from_config(cfg)
    assert scripts.get_heads()==['0017_booked_interview_email']
    assert scripts.get_revision('head').down_revision=='0016_submission_deletion'
    output=StringIO();cfg.output_buffer=output;command.upgrade(cfg,'0016_submission_deletion:head',sql=True)
    sql=output.getvalue();assert 'PRIMARY KEY (interview_id)' in sql and 'FOREIGN KEY(interview_id)' in sql
    assert 'scheduling_invitation_id' not in sql and 'recipient' not in sql and 'token' not in sql
    output.seek(0);output.truncate();command.downgrade(cfg,'head:0016_submission_deletion',sql=True)
    assert 'booked_email_journal_not_empty' in output.getvalue()
