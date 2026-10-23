"""Connected real-service/PG flow; synthetic recognizer and evaluation provider only.

Opt-in pg fixture creates its own container. No preserved database is used.
"""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.requests import Request

from app.main import app
from app.core.auth import database_session, token_hash, current_recruiter
from app.db.models.recruiter import Recruiter, RecruiterSession, JobProfile, CandidateScoreRecord, InterviewInvitation
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture
from app.schemas.candidate_score import ScoringWeights
from app.services.interview_transcripts import StorageConsentAuthority, TranscriptPersistenceService, TranscriptError
from app.schemas.interview_transcript import FinalTranscriptEvent
from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
from app.services.caption_transcript import CaptionTranscript
from app.services.interview_captions import CaptionSession
from app.services.evaluation_input import PostInterviewInputService, EvaluationInputError
from app.services.durable_interview_analysis import DurableAnalysisManager
from app.services.consolidated_assessment import consolidated_assessment
from app.agents.evaluation.workflow import InterviewEvaluationWorkflow, ModelAssessment
from app.rag.technical_references import CuratedTechnicalRetriever
from test_interview_transcripts import pg
from test_caption_finalization import end
from test_candidate_scoring import scored
from test_interview_evaluation import FakeProvider, assessment


class GroundedProvider(FakeProvider):
    async def assess(self, source, pairs, mappings, references, repair=False, repair_error=None):
        if self.fail:
            return await super().assess(source, pairs, mappings, references, repair, repair_error=repair_error)
        self.calls += 1
        value = assessment(pairs).model_dump(mode='json')
        value['answers'][0]['dimensions'][0].update(status='supported',
            evidence=[{'turn_id': str(pairs[0].answer_turns[0]), 'quote': 'ordered collection'}])
        return ModelAssessment.model_validate(value)


@pytest.fixture(autouse=True)
def no_external_inference(monkeypatch):
    async def denied(*args, **kwargs):
        pytest.fail('External provider requests are forbidden in this integration test')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', denied)


@pytest.mark.parametrize('outcome,epochs', [('complete',1), ('interrupted',1), ('missing_speaker',1), ('provider_failure',1), ('complete',2), ('interrupted',2), ('revoked',2), ('missing_consent',2)])
def test_connected_scheduled_capture_analysis_assessment(pg, monkeypatch, outcome, epochs):
    async def scenario():
        assert pg.database == 'transcript_test' and pg.port == 54402
        engine = create_async_engine(pg, hide_parameters=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        now = [datetime.now(timezone.utc)]
        owner, foreign, job, batch, upload = (uuid4() for _ in range(5))
        # Fictional sessions provision identity only; production auth checks still run.
        recruiter_token, candidate_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        foreign_token = secrets.token_urlsafe(32)
        score, _, criteria = await asyncio.to_thread(scored, ['supported'], weights=ScoringWeights(skill=100, experience=0, education=0))
        reference = 'TT-JOB-' + job.hex[:16].upper()
        score = score.model_copy(update={'job_reference': reference, 'upload_id': upload})
        snapshot = dict(job_reference=reference, job_title='Synthetic Python role', criteria_confirmed=True,
            criteria=[c.model_copy(update={'description': 'Python'}).model_dump(mode='json') for c in criteria])
        def request(candidate=False, token=None):
            cookie = ('talenttrace_interview=' + candidate_token) if candidate else ('talenttrace_session=' + (token or recruiter_token))
            return Request({'type': 'http', 'method': 'POST', 'path': '/synthetic', 'headers': [
                (b'cookie', cookie.encode()), (b'x-talenttrace-request', b'1'),
                (b'x-talenttrace-storage-consent', CONSENT_VERSION.encode())]})
        managers = []
        caption = None
        try:
            async with factory.begin() as db:
                db.add(Recruiter(id=owner, email=f'{owner}@example.invalid', password_hash='unused', active=True))
                db.add(Recruiter(id=foreign, email=f'{foreign}@example.invalid', password_hash='unused', active=True))
                await db.flush()
                db.add(RecruiterSession(token_hash=token_hash(recruiter_token), recruiter_id=owner, expires_at=now[0]+timedelta(hours=1)))
                db.add(RecruiterSession(token_hash=token_hash(foreign_token), recruiter_id=foreign, expires_at=now[0]+timedelta(hours=1)))
                db.add(JobProfile(id=job, recruiter_id=owner, job_reference=reference, job_title=snapshot['job_title'],
                    revision=2, confirmed_snapshot=snapshot, sources=[], suggestions={}, scoring_weights=score.weights.model_dump()))
                await db.flush()
                db.add(CandidateScoreRecord(job_id=job, batch_id=batch, upload_id=upload, criteria_revision=2,
                    scoring_version='f2-coverage-v1', score=score.score, payload=score.model_dump(mode='json')))
            async def sessions():
                async with factory() as db:
                    yield db
            monkeypatch.setitem(app.dependency_overrides, database_session, sessions)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post(f'/api/v1/jobs/{job}/interviews', headers={
                    'cookie': 'talenttrace_session='+recruiter_token, 'x-talenttrace-request': '1'}, json={
                    'batch_id': str(batch), 'upload_id': str(upload), 'criteria_revision': 2,
                    'selection_confirmed': True, 'scheduled_at': (now[0]+timedelta(minutes=1)).isoformat(),
                    'timezone': 'Asia/Dhaka', 'duration_minutes': 30})
                assert response.status_code == 201
                interview = UUID(response.json()['id'])
                assert response.json()['job_id'] == str(job) and response.json()['upload_id'] == str(upload)
            async with factory.begin() as db:
                # Candidate claim/session issuance is simulated, never exchanged externally.
                db.add(InterviewInvitation(interview_id=interview, token_hash=token_hash(str(uuid4())),
                    candidate_session_hash=token_hash(candidate_token), revoked=False, expires_at=now[0]+timedelta(hours=1)))
            authority = StorageConsentAuthority(factory, version=CONSENT_VERSION, clock=lambda: now[0])
            storage = TranscriptPersistenceService(factory, authority, clock=lambda: now[0])
            coordinator = TranscriptConsentCoordinator(authority, storage, enabled=True)
            tick = [0.0]
            deadline = (datetime.fromisoformat(response.json()['scheduled_at']) + timedelta(minutes=45) - now[0]).total_seconds()
            capture_ids = []
            class Worker:
                async def start(self): pass
                async def close(self): pass
                async def transcribe(self, pcm): return 'unused'
            messages = []
            async def send(event): messages.append(event)
            for epoch in range(epochs):
                if epoch:
                    async with factory() as db:
                        prior = await db.get(Capture, capture_ids[-1])
                        assert prior.status in ('completed', 'interrupted')
                    now[0] += timedelta(seconds=3); tick[0] += 3
                    if outcome == 'revoked':
                        await authority.withdraw(request(True), interview_id=interview)
                        old = turns[0]
                        event = FinalTranscriptEvent(**{k:getattr(old,k) for k in ('id','session_id','sequence','role','text','start_ms','end_ms')}, final=True)
                        with pytest.raises(TranscriptError, match='storage_authorization_revoked'):
                            await storage.append_final(owner, event)
                        with pytest.raises(TranscriptError, match='storage_authorization_revoked'):
                            await coordinator.prepare(request(), interview_id=interview, job_id=job)
                        return
                    for req, other_job, other_interview in ((request(), uuid4(), interview),
                            (request(token=foreign_token), job, interview), (request(True), None, uuid4())):
                        with pytest.raises(TranscriptError):
                            await coordinator.prepare(req, interview_id=other_interview, job_id=other_job)
                prepared = await coordinator.prepare(request(), interview_id=interview, job_id=job)
                capture_id = prepared['capture_id']
                assert capture_id not in capture_ids
                if epoch:
                    with pytest.raises(TranscriptError):
                        await coordinator.decide(request(True), interview_id=interview, capture_id=capture_ids[-1], decision='accept')
                await coordinator.decide(request(), interview_id=interview, capture_id=capture_id, decision='accept', job_id=job)
                if outcome == 'missing_consent' and epoch:
                    async with factory() as db: assert await db.get(Capture, capture_id) is None
                    assert coordinator._entries[interview].status == 'awaiting_consent'
                    return
                await coordinator.decide(request(True), interview_id=interview, capture_id=capture_id, decision='accept')
                capture_ids.append(capture_id)
                adapter = CaptionTranscript(N(storage=storage, coordinator=coordinator), interview)
                caption = CaptionSession(Worker, clock=lambda: tick[0], storage=adapter, authorization_deadline=deadline)
                assert caption.authorization_deadline == deadline
                for role in ('recruiter', 'candidate'): await caption.connect(role, send)
                for role in ('recruiter', 'candidate'): await caption.approve(role)
                for role, text in [('recruiter', 'What is a Python list?'), ('candidate', 'A list is an ordered collection.')]:
                    if outcome == 'missing_speaker' and role == 'candidate': continue
                    async def recognize(pcm, text=text): return text
                    caption.providers[role].transcribe = recognize
                    for _ in range(40):
                        tick[0] += .1; now[0] += timedelta(seconds=.1)
                        await caption.audio(role, bytes(3200))
                interrupted = outcome == 'interrupted' and epoch == 0
                if interrupted:
                    await caption.stop()
                else:
                    await caption.request_finish('recruiter')
                    for role in ('recruiter', 'candidate'): await end(caption, role)
                    await caption.finalizer
                    assert caption.final_result['outcome'] == 'drained'
                async with factory() as db:
                    capture = await db.get(Capture, capture_id)
                    assert capture.status == ('interrupted' if interrupted else 'completed')
                    assert capture.persistence_outcome == ('partial' if interrupted else 'saved')
                turns = await storage.list_turns(owner, interview)
                if epoch and outcome == 'complete':
                    old = turns[0]
                    duplicate = FinalTranscriptEvent(**{k:getattr(old,k) for k in ('id','session_id','sequence','role','text','start_ms','end_ms')}, final=True)
                    await storage.append_final(owner, duplicate)
                    late = duplicate.model_copy(update={'id':uuid4(),'sequence':3})
                    with pytest.raises(TranscriptError, match='capture_closed'):
                        await storage.append_final(owner, late)
                    assert len(await storage.list_turns(owner, interview)) == 4
            assert [t.role for t in turns] == (['recruiter'] if outcome == 'missing_speaker' else ['recruiter', 'candidate'] * epochs)
            assert {t.session_id for t in turns} == set(capture_ids)
            assert all(t.start_ms <= t.end_ms for t in turns)
            provider = GroundedProvider(fail=outcome == 'provider_failure')
            def manager():
                value = DurableAnalysisManager(PostInterviewInputService(storage),
                    InterviewEvaluationWorkflow(provider, CuratedTechnicalRetriever()), [job])
                managers.append(value)
                return value
            analysis = manager()
            operation = uuid4()
            if outcome in ('interrupted', 'missing_speaker'):
                with pytest.raises(EvaluationInputError):
                    await analysis.start(request(), job, interview, 2, operation)
                assert provider.calls == 0
            else:
                await analysis.start(request(), job, interview, 2, operation)
                await analysis.operations[operation].task
                result = await manager().get(request(), job, interview, operation)
                assert result['status'] == ('failed' if outcome == 'provider_failure' else 'completed')
                if outcome == 'provider_failure': assert result['result'] is None
                if outcome == 'complete': assert provider.calls == 1
            with pytest.raises(EvaluationInputError):
                await PostInterviewInputService(storage).prepare(request(), job_id=job, interview_id=interview, revision=3)
            async def report(job_id=job, upload_id=upload, user=owner):
                async with factory() as db:
                    req = request(token=foreign_token if user == foreign else recruiter_token)
                    actor = await current_recruiter(req, db)
                    return await consolidated_assessment(db, req, actor, job_id, batch, upload_id, storage_enabled=True)
            first, second = await report(), await report()
            assert first.model_dump(mode='json') == second.model_dump(mode='json')
            assert first.cv.score == 100 and first.upload_id == upload
            if outcome == 'complete':
                assert first.interview.state == 'available'
                assert {t.id for t in first.interview.turns} == {t.id for t in turns}
                quotes = [q for answer in first.interview.assessment.answers for dimension in answer.dimensions for q in dimension.evidence]
                assert quotes and all(q.turn_id in {t.id for t in turns if t.role == 'candidate'} for q in quotes)
                if epochs == 2:
                    assert '3000 ms between stored capture windows' in first.interview.warning
                    assert 'Transition audio coverage is unverified' in first.interview.warning
                    assert {pair.capture_id for pair in first.interview.pairs} == set(capture_ids)
            else:
                assert first.interview.state != 'available' and first.interview.assessment is None
            for kwargs in ({'job_id': uuid4()}, {'upload_id': uuid4()}, {'user': foreign}):
                with pytest.raises(HTTPException): await report(**kwargs)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                denied = await client.get(f'/api/v1/jobs/{job}/batches/{batch}/candidates/{upload}/assessment',
                    headers={'cookie': 'talenttrace_interview='+candidate_token})
                assert denied.status_code == 401
        finally:
            if caption and not caption.stopped: await caption.stop()
            for m in managers: await m.close()
            await engine.dispose()
    asyncio.run(scenario())
