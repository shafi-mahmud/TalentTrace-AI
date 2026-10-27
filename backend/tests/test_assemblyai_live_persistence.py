"""Real authenticated APIs/PG, mocked WSS. Requires an explicitly test-owned database.

The ignored Task 4 launcher supplies its unique resource manifest. Never accepts
an arbitrary deployment database or creates/migrates a database during collection.
"""
import asyncio
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.main import app
from app.core.config import settings
from app.core.auth import session_factory,hash_password
from app.db.session import create_database_engine,create_database_session_factory
from app.db.models.recruiter import Recruiter,JobProfile,CandidateScoreRecord
from app.schemas.candidate_score import ScoringWeights
from app.integrations.stt import assemblyai_live as adapter
from app.integrations.stt.assemblyai_synthetic import fixture_pcm
from app.api.routers import interview_captions as route
from test_candidate_scoring import scored
from test_assemblyai_live import Socket


def owned_pg():
    value=os.environ.get('TASK4_PG_MANIFEST')
    if not value:pytest.skip('Explicit new Task 4 PostgreSQL resource required')
    manifest=json.loads(Path(value).read_text())
    url=make_url(settings.database_url.get_secret_value())
    assert (url.host=='127.0.0.1' and url.port==manifest['port']
        and url.database==manifest['database'] and url.database.startswith('task4_live_')
        and manifest['new_resource_verified'] is True)
    async def verify():
        engine=create_database_engine()
        try:
            async with create_database_session_factory(engine)() as db:
                assert (await db.execute(text('select current_database()'))).scalar_one()==manifest['database']
                assert (await db.execute(text('select version_num from alembic_version'))).scalar_one()=='0017_booked_interview_email'
        finally:await engine.dispose()
    asyncio.run(verify())
    return manifest


def fixture():
    async def seed():
        owner,foreign,job,batch,upload=(uuid4() for _ in range(5))
        password=secrets.token_urlsafe(24)
        score,_,criteria=await asyncio.to_thread(scored,['supported'],weights=ScoringWeights(skill=100,experience=0,education=0))
        reference='TT-JOB-'+job.hex[:16].upper()
        score=score.model_copy(update={'job_reference':reference,'upload_id':upload})
        snapshot=dict(job_reference=reference,job_title='Fictional Task 4 speech test',criteria_confirmed=True,
            criteria=[c.model_copy(update={'description':'Python'}).model_dump(mode='json') for c in criteria])
        encoded=await asyncio.to_thread(hash_password,password)
        engine=create_database_engine()
        async with create_database_session_factory(engine)() as db:
            db.add_all([Recruiter(id=owner,email=f'{owner}@example.invalid',password_hash=encoded,active=True),
                Recruiter(id=foreign,email=f'{foreign}@example.invalid',password_hash=encoded,active=True)])
            await db.flush()
            db.add(JobProfile(id=job,recruiter_id=owner,job_reference=reference,job_title=snapshot['job_title'],revision=2,
                confirmed_snapshot=snapshot,sources=[],suggestions={},scoring_weights=score.weights.model_dump()))
            await db.flush()
            db.add(CandidateScoreRecord(job_id=job,batch_id=batch,upload_id=upload,criteria_revision=2,
                scoring_version='f2-coverage-v1',score=score.score,payload=score.model_dump(mode='json')))
            await db.commit()
        await engine.dispose()
        return dict(owner=str(owner),foreign=str(foreign),job=str(job),batch=str(batch),upload=str(upload),password=password)
    return asyncio.run(seed())


def authenticated_fixture(stack):
    f=fixture()
    headers={'origin':'http://localhost:5173','x-talenttrace-request':'1'}
    transport=stack.enter_context(TestClient(app,headers=headers))
    class RoleClient:
        def __init__(self):self.cookies=httpx.Cookies()
        def headers(self,path):
            request=httpx.Request('GET',str(transport.base_url.join(path)))
            self.cookies.set_cookie_header(request)
            return {'cookie':request.headers.get('cookie','')}
        def get(self,path):return transport.get(path,headers=self.headers(path))
        def post(self,path,**kw):
            headers=self.headers(path)
            if path.endswith('/decision'):
                headers['x-talenttrace-storage-consent']='optional-transcript-storage-v1'
            response=transport.post(path,headers=headers,**kw)
            for cookie in response.cookies.jar:self.cookies.jar.set_cookie(cookie)
            return response
        def websocket_connect(self,path):return transport.websocket_connect(path,headers=self.headers(path))
    recruiter,candidate,foreign=RoleClient(),RoleClient(),RoleClient()
    for client,identity in [(recruiter,f['owner']),(foreign,f['foreign'])]:
        assert client.post('/api/v1/auth/login',json={'email':identity+'@example.invalid','password':f['password']}).status_code==200
    response=recruiter.post(f"/api/v1/jobs/{f['job']}/interviews",json=dict(batch_id=f['batch'],upload_id=f['upload'],
        criteria_revision=2,selection_confirmed=True,scheduled_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
        timezone='Asia/Dhaka',duration_minutes=15))
    assert response.status_code==201
    f['interview']=response.json()['id']
    f['path']=f"/api/v1/jobs/{f['job']}/interviews/{f['interview']}"
    issued=recruiter.post(f['path']+'/invitation',json={'expires_in_hours':1})
    assert issued.status_code==200
    assert candidate.post('/api/v1/interview-access/exchange',json={'token':issued.json()['token']}).status_code==200
    return f,recruiter,candidate,foreign


def run_connected(*, real=False, storage=True, monkeypatch=None, evidence=None):
    if evidence is not None:evidence['stage']='database_preflight'
    owned_pg()
    from app.services.transcript_runtime import runtime
    runtime.cache_clear()
    session_factory.cache_clear()
    with ExitStack() as stack:
        f,recruiter,candidate,foreign=authenticated_fixture(stack)
        if evidence is not None:evidence['stage']='authenticated_storage_consent'
        assert foreign.get(f['path']+'/transcript').status_code!=200
        assert candidate.get(f['path']+'/transcript').status_code!=200
        assessment=f"/api/v1/jobs/{f['job']}/batches/{f['batch']}/candidates/{f['upload']}/assessment"
        assert candidate.get(assessment).status_code==401
        assert foreign.get(assessment).status_code==404
        assert foreign.post(f['path']+'/transcript-storage/prepare',json={}).status_code!=200
        prepared=recruiter.post(f['path']+'/transcript-storage/prepare',json={})
        other=candidate.post('/api/v1/interview-access/transcript-storage/prepare',json={})
        assert prepared.status_code==other.status_code==200
        capture=prepared.json()['capture_id'];assert capture==other.json()['capture_id']
        for client,path in [(recruiter,f['path']+'/transcript-storage'),(candidate,'/api/v1/interview-access/transcript-storage')]:
            decision='accept' if storage else 'decline'
            assert client.post(path+'/decision',json={'capture_id':capture,'decision':decision}).status_code==200
        from uuid import UUID
        configuration=type(settings)(_env_file=None,**{**settings.model_dump(),
            'assemblyai_live_enabled':True,'assemblyai_live_interview_id':UUID(f['interview'])})
        old=route.settings;route.settings=configuration
        try:
            for unauthorized in (candidate,foreign):
                with pytest.raises(WebSocketDisconnect):
                    with unauthorized.websocket_connect(f['path']+'/captions'):pass
            original=adapter.AssemblyAILiveStream
            observed=[]
            async def connect(*a,**kw):return Socket()
            def tracked(key,final,failure):
                assert len(observed)<2
                provider=original(key,final,failure,**({} if real else {'connector':connect}))
                observed.append(provider)
                return provider
            monkeypatch.setattr(adapter,'AssemblyAILiveStream',tracked)
            events={role:[] for role in ('recruiter','candidate')}
            if evidence is not None:evidence['stage']='caption_websockets'
            counts={role:dict(frames=0,samples=0) for role in events}
            with recruiter.websocket_connect(f['path']+'/captions') as r, candidate.websocket_connect('/api/v1/interview-access/captions') as c:
                r.receive_json();c.receive_json()
                r.send_text('consent');c.send_text('consent')
                def reader(role,ws):
                    while True:
                        value=ws.receive_json()
                        events[role].append(value)
                        if value['kind']=='finishing':
                            ws.send_json(dict(kind='end',**counts[role],captured_samples=counts[role]['samples']))
                        if value['kind']=='stopped':return
                with ThreadPoolExecutor(max_workers=2) as pool:
                    readers=[pool.submit(reader,role,ws) for role,ws in [('recruiter',r),('candidate',c)]]
                    deadline=time.monotonic()+12
                    while not all(any(e['kind']=='active' for e in values) for values in events.values()):
                        if time.monotonic()>deadline:raise RuntimeError('caption_start_unconfirmed')
                        time.sleep(.01)
                    pcm={role:fixture_pcm(role) if real else bytes(3200) for role in events}
                    if evidence is not None:evidence['stage']='synthetic_pcm_streaming'
                    limit=max(map(len,pcm.values())); start=time.monotonic()
                    for offset in range(0,limit,3200):
                        for role,ws in [('recruiter',r),('candidate',c)]:
                            frame=pcm[role][offset:offset+3200];frame=frame+bytes(3200-len(frame))
                            counts[role]['frames']+=1;counts[role]['samples']+=1600
                            ws.send_bytes(frame)
                        time.sleep(max(0,start+(offset+3200)/32000-time.monotonic()))
                    r.send_text('finish')
                    if evidence is not None:evidence['stage']='normal_finalization'
                    for future in readers:future.result(timeout=40)
            captions=[e for e in events['recruiter'] if e['kind']=='caption']
            result=dict(real_provider=real,storage_enabled=storage,caption_count=len(captions),
                roles=sorted({e['role'] for e in captions}),nonempty=all(bool(e['text'].strip()) for e in captions),
                unique_sequences=len({e['sequence'] for e in captions})==len(captions),
                ordered_intervals=all(0<=e['start']<=e['end']<=120 for e in captions),
                termination_confirmed=any(e['kind']=='provider-termination' and e['confirmed'] and e['sessions']==2 for e in events['recruiter']),
                drained=any(e['kind']=='finalized' and e['outcome']=='drained' for e in events['recruiter']))
            result['provider_streams']=len(observed)
            result['usage']=[p.usage for p in observed]
            result['provider_failures']=[p.failure for p in observed]
            page=recruiter.get(f['path']+'/transcript')
            assert page.status_code==200 if storage else page.status_code!=200
            rows=page.json()['turns'] if storage else []
            result['persisted_turns']=len(rows)
            if storage:
                result['capture_completed']=any(row['status']=='completed' and row['outcome']=='saved' for row in page.json()['captures'])
                # New authenticated GET reads persisted rows, not the WebSocket event buffer.
                reloaded=recruiter.get(f['path']+'/transcript')
                result['reload_consistent']=reloaded.status_code==200 and [t['id'] for t in reloaded.json()['turns']]==[t['id'] for t in rows]
                revoked=candidate.post('/api/v1/interview-transcripts/privacy/withdraw',json={})
                result['withdrawal_verified']=revoked.status_code==200 and revoked.json()['withdrawn'] and revoked.json()['deletion_verified']
                denied=recruiter.get(f['path']+'/transcript')
                result['retrieval_denied_after_withdrawal']=denied.status_code!=200
            if evidence is not None:evidence.update(result)
            assert result['roles']==['candidate','recruiter'] and result['nonempty'] and result['unique_sequences'] and result['ordered_intervals']
            assert result['termination_confirmed'] and result['drained']
            if storage:assert len(rows)==len(captions) and result['capture_completed'] and result['reload_consistent'] and result['withdrawal_verified'] and result['retrieval_denied_after_withdrawal']
            else:assert not rows
            return result
        finally:
            if evidence is not None and 'observed' in locals():
                evidence['stream_attempts']=sum(p.attempted for p in observed)
                evidence['stream_termination_confirmed']=[p.termination_confirmed for p in observed]
                evidence['provider_usage']=[p.usage for p in observed]
                evidence['provider_errors']=[p.failure for p in observed]
                evidence['event_counts']={role:{kind:sum(e['kind']==kind for e in values)
                    for kind in ('active','caption','finalized','storage','provider-termination','stopped','error')}
                    for role,values in events.items()} if 'events' in locals() else {}
            route.settings=old


@pytest.mark.parametrize('storage',[False,True])
def test_authenticated_pg_live_capture_and_privacy(monkeypatch,storage):
    run_connected(storage=storage,monkeypatch=monkeypatch)
