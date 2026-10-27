"""Authenticated self-scheduling against a separately opted-in disposable database."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_authenticated_self_scheduling_and_fake_mail(monkeypatch):
    url = os.environ.get('SELF_SCHEDULING_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Dedicated disposable PostgreSQL required')
    target = make_url(url)
    assert target.database == 'schedule_test' and target.port == 54401
    from app.main import app
    from app.core.auth import hash_password, token_hash
    from app.db.models.recruiter import (Recruiter, CandidateScoreRecord,
        SchedulingInvitation, InterviewInvitation, InterviewEmailAttempt)
    from app.schemas.candidate_score import ScoringWeights
    from app.services import interview_email as delivery
    from test_interview_email import Fake
    from test_candidate_scoring import scored
    fake = Fake()
    monkeypatch.setattr(delivery, 'SMTPTransport', lambda: fake)

    async def run():
        engine = create_async_engine(url, hide_parameters=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        # Keep connections on this test's loop, independent of earlier TestClient loops.
        monkeypatch.setattr('app.core.auth.session_factory', lambda: sessions)
        owner, foreign = uuid4(), uuid4()
        password = secrets.token_urlsafe(24)
        async with sessions.begin() as db:
            assert (await db.execute(text('select current_database()'))).scalar_one() == 'schedule_test'
            assert (await db.execute(text('select version_num from alembic_version'))).scalar_one() == '0017_booked_interview_email'
            for identity in (owner, foreign):
                db.add(Recruiter(id=identity, email=f'{identity}@synthetic.invalid',
                    password_hash=hash_password(password), active=True))
        score, _, criteria = await asyncio.to_thread(scored, ['supported'], weights=ScoringWeights(skill=100, experience=0, education=0))
        headers = {'X-TalentTrace-Request': '1'}
        transport = httpx.ASGITransport(app, client=('self-schedule-acceptance', 50000))
        async with httpx.AsyncClient(transport=transport, base_url='http://test', headers=headers) as recruiter, \
                httpx.AsyncClient(transport=transport, base_url='http://test', headers=headers) as other, \
                httpx.AsyncClient(transport=transport, base_url='http://test', headers=headers) as candidate:
            for client, identity in ((recruiter, owner), (other, foreign)):
                assert (await client.post('/api/v1/auth/login', json={'email': f'{identity}@synthetic.invalid', 'password': password})).status_code == 200
            result = await recruiter.post('/api/v1/jobs', json={'job_title': 'Synthetic self-scheduling acceptance'})
            assert result.status_code == 201
            job = result.json(); job_id = job['id']
            assert (await recruiter.put(f'/api/v1/jobs/{job_id}/criteria', json={
                'revision': 1, 'confirmed': True, 'criteria': [c.model_dump(mode='json') for c in criteria],
                'weights': score.weights.model_dump()})).status_code == 200
            batch = uuid4(); uploads = [uuid4() for _ in range(4)]
            async with sessions.begin() as db:
                for upload in uploads:
                    value = score.model_copy(update={'job_reference': job['job_reference'], 'upload_id': upload})
                    db.add(CandidateScoreRecord(job_id=UUID(job_id), batch_id=batch, upload_id=upload,
                        criteria_revision=2, scoring_version='f2-coverage-v1', score=value.score, payload=value.model_dump(mode='json')))
            selections = [dict(batch_id=str(batch), upload_id=str(upload), criteria_revision=2, selection_confirmed=True) for upload in uploads]
            invitation_path = f'/api/v1/jobs/{job_id}/scheduling-invitations'
            assert (await candidate.post(invitation_path, json=selections[0])).status_code == 401
            assert (await other.post(invitation_path, json=selections[0])).status_code == 404
            assert (await recruiter.post(invitation_path, json={**selections[0], 'upload_id': str(uuid4())})).status_code == 409
            assert (await recruiter.post(invitation_path, json={**selections[0], 'criteria_revision': 1})).status_code == 409
            assert (await recruiter.post(invitation_path+'/email', json={**selections[0], 'recipient': 'unapproved@synthetic.invalid'})).status_code == 422
            email = {**selections[0], 'recipient': 'approved@synthetic.invalid'}
            assert (await recruiter.post(invitation_path+'/email', json=email)).json() == {'email_status': 'accepted', 'reused': False}
            assert len(fake.messages) == 1
            body = fake.messages[0][-1]
            assert '/interview-schedule#schedule=' in body and 'seven days' in body
            token = body.split('#schedule=', 1)[1].split()[0]
            assert (await recruiter.post(invitation_path+'/email', json=email)).json() == {'email_status': 'accepted', 'reused': True}
            assert len(fake.messages) == 1
            cap = {'token': token}
            assert (await candidate.post('/api/v1/interview-scheduling/slots', json=cap, headers={'X-TalentTrace-Request': ''})).status_code == 403
            slots = await candidate.post('/api/v1/interview-scheduling/slots', json=cap)
            assert slots.status_code == 200 and slots.json()['timezone'] == 'Asia/Dhaka'
            start = slots.json()['slots'][0]
            booking = await candidate.post('/api/v1/interview-scheduling/book', json={**cap, 'scheduled_at': start})
            assert booking.status_code == 201 and booking.json()['email_status'] == 'accepted'
            booked = booking.json(); interview = booked['interview']
            assert interview['job_id'] == job_id and interview['upload_id'] == str(uploads[0])
            assert interview['duration_minutes'] == 60 and interview['timezone'] == 'Asia/Dhaka'
            assert len(fake.messages) == 2
            message = fake.messages[1][-1]
            from zoneinfo import ZoneInfo
            expected = datetime.fromisoformat(start).astimezone(ZoneInfo('Asia/Dhaka'))
            assert f'{expected:%d %B %Y}' in message and f'{expected:%H:%M}' in message
            assert f'{expected+timedelta(hours=1):%H:%M}' in message and '60 minutes' in message
            assert '/interview-join#invite=' + booked['joining_token'] in message
            async with sessions() as db:
                saved = await db.scalar(select(InterviewInvitation).where(InterviewInvitation.token_hash == token_hash(booked['joining_token'])))
                assert str(saved.interview_id) == interview['id'] and saved.candidate_session_hash is None
                invitation = await db.scalar(select(SchedulingInvitation).where(SchedulingInvitation.token_hash == token_hash(token)))
                assert str(invitation.interview_id) == interview['id']
                attempts = (await db.scalars(select(InterviewEmailAttempt).where(InterviewEmailAttempt.scheduling_invitation_id == invitation.id))).all()
                assert sorted((a.kind, a.status) for a in attempts) == [('confirmation', 'accepted'), ('scheduling', 'accepted')]
            assert (await candidate.post('/api/v1/interview-scheduling/book', json={**cap, 'scheduled_at': start})).status_code == 409
            token2 = (await recruiter.post(invitation_path, json=selections[1])).json()['token']
            assert (await candidate.post('/api/v1/interview-scheduling/book', json={'token': token2, 'scheduled_at': start})).status_code == 409
            assert start not in (await candidate.post('/api/v1/interview-scheduling/slots', json={'token': token2})).json()['slots']
            fresh = await recruiter.get(f'/api/v1/jobs/{job_id}/interviews')
            assert fresh.status_code == 200 and fresh.json()[0] == interview
            assert (await other.get(f'/api/v1/jobs/{job_id}/interviews')).status_code == 404
            assert (await candidate.get(f'/api/v1/jobs/{job_id}/interviews')).status_code == 401
            expired = (await recruiter.post(invitation_path, json=selections[2])).json()['token']
            async with sessions.begin() as db:
                row = await db.scalar(select(SchedulingInvitation).where(SchedulingInvitation.token_hash == token_hash(expired)))
                row.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            assert (await candidate.post('/api/v1/interview-scheduling/slots', json={'token': expired})).status_code == 401
            assert (await candidate.post('/api/v1/interview-scheduling/slots', json={'token': secrets.token_urlsafe(32)})).status_code == 401
            # Simulate an interrupted durable reservation: it must never resend.
            payload = {**selections[3], 'recipient': 'approved@synthetic.invalid'}
            assert (await recruiter.post(invitation_path+'/email', json=payload)).status_code == 200
            async with sessions.begin() as db:
                row = await db.scalar(select(SchedulingInvitation).where(SchedulingInvitation.upload_id == uploads[3]))
                attempt = await db.scalar(select(InterviewEmailAttempt).where(InterviewEmailAttempt.scheduling_invitation_id == row.id))
                attempt.status = 'sending'
            count = len(fake.messages)
            assert (await recruiter.post(invitation_path+'/email', json=payload)).json() == {'email_status': 'uncertain', 'reused': True}
            assert len(fake.messages) == count
        await engine.dispose()
    asyncio.run(run())
