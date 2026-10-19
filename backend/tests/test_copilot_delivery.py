"""Offline 5B integration: real routes/auth with synthetic transactional SQL double."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import socket
import threading
from uuid import uuid4

import pytest
from app.services.copilot_delivery import Access, Delivery, Unavailable, VERSION
from app.schemas.interview_copilot import Requirement, Event, Source, Update
from app.api.routers import interview_copilot as route
from app.core.config import settings
from app.db.models.recruiter import InterviewInvitation, JobProfile, InterviewSchedule, RecruiterSession
from test_recruiter_records import workspace, client, login
from test_interview_access import invitation_workspace


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):raise AssertionError('No provider/network permitted')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    original=socket.socket.connect
    def no_external(self,address):
        # Windows asyncio creates its local self-pipe with socketpair().
        if isinstance(address,tuple) and address[0]=='127.0.0.1':
            return original(self,address)
        return forbidden()
    monkeypatch.setattr(socket.socket, 'connect', no_external)
    import httpx
    async def no_http(*args,**kwargs):raise AssertionError('No real HTTP transport')
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',no_http)


@pytest.fixture
def runtime():
    clock=[100.0]
    manager=Delivery(clock=lambda:clock[0])
    access=Access(uuid4(),uuid4(),2,uuid4(),'synthetic-owner-hash','synthetic-candidate-hash',
        (Requirement(id='python',description='Python'),Requirement(id='sql',description='SQL')),1000)
    manager.prepare(access)
    return manager,access,clock


def consent(manager,access,role):
    value=manager.view(access)
    from uuid import UUID
    return manager.decide(access,role,UUID(value['run_id']),value['epoch'],'accept')


def events(manager,access,generation=1):
    binding=manager.runs[access.interview].binding
    return Update(synthetic=True,binding=binding,generation=generation,events=tuple(
        Event(interview_id=binding.interview_id,run_id=binding.run_id,criteria_revision=2,
            generation=generation,source=Source(caption_run_id=binding.caption_run_id,sequence=i+1),
            role=role,timestamp_ms=1000+i*1000,text=text)
        for i,(role,text) in enumerate([('recruiter','Explain Python lists.'),('candidate','Lists are mutable ordered sequences.')])) )


def authorized(runtime):
    manager,access,clock=runtime
    consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
    return manager,access,clock


def test_two_independent_consents_no_replay_and_role_minimization(runtime):
    manager,access,clock=runtime
    consent(manager,access,'recruiter')
    with pytest.raises(Unavailable):manager.submit_synthetic(access,events(manager,access))
    assert manager.view(access)['status']=='awaiting_consent'
    consent(manager,access,'candidate');clock[0]=106
    value=manager.submit_synthetic(access,events(manager,access))
    assert value['suggestion']['requirement']=='Python'
    assert 'suggestion' not in manager.view(access) and 'processing' not in manager.view(access)
    assert not manager.view(access)['live_connected']


def test_preconsent_events_are_refused(runtime):
    manager,access,clock=runtime
    clock[0]=105;consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=110
    with pytest.raises(Unavailable):manager.submit_synthetic(access,events(manager,access))


@pytest.mark.parametrize('change',['revision','requirements','candidate','recruiter','blocked','deadline'])
def test_changed_scope_clears_results_and_consents(runtime,change):
    manager,access,clock=authorized(runtime);manager.submit_synthetic(access,events(manager,access))
    changes={'revision':{'revision':3},'requirements':{'requirements':(Requirement(id='sql',description='SQL'),)},
        'candidate':{'candidate_key':'replacement'},'recruiter':{'recruiter_key':'replacement'},
        'blocked':{'blocked':True},'deadline':{'deadline':101}}
    view=manager.view(replace(access,**changes[change]),recruiter=True)
    assert view['suggestion'] is None and not view['recruiter_consented']


def test_withdrawal_restart_dismiss_and_expiry(runtime):
    manager,access,clock=authorized(runtime)
    value=manager.submit_synthetic(access,events(manager,access))
    from uuid import UUID
    manager.dismiss(access,UUID(value['run_id']),value['epoch'],value['suggestion']['id'])
    assert manager.view(access,recruiter=True)['suggestion'] is None
    clock[0]=122
    assert manager.submit_synthetic(access,events(manager,access,2))['suggestion'] is None
    view=manager.view(access)
    manager.decide(access,'candidate',UUID(view['run_id']),view['epoch'],'withdraw')
    assert manager.view(access)['status']=='withdrawn'
    with pytest.raises(Unavailable):consent(manager,access,'recruiter')
    assert Delivery().view(access)['status']=='unavailable'
    clock[0]=221;manager.sweep();assert not manager.runs


@pytest.mark.parametrize('replacement',[False,True])
def test_inflight_work_cannot_publish_after_withdrawal_or_run_replacement(runtime,replacement):
    manager,access,clock=authorized(runtime);run=manager.runs[access.interview]
    entered=threading.Event();release=threading.Event();original=run.logic.process
    def delayed(**kwargs):entered.set();assert release.wait(5);return original(**kwargs)
    run.logic.process=delayed
    errors=[]
    def work():
        try:manager.submit_synthetic(access,events(manager,access))
        except Unavailable:errors.append('fenced')
    thread=threading.Thread(target=work);thread.start();assert entered.wait(5)
    if replacement:manager.prepare(access)
    else:manager.invalidate(access.interview)
    release.set();thread.join(5)
    assert errors==['fenced'] and manager.view(access,recruiter=True)['suggestion'] is None


def test_single_work_slot_result_ttl_and_unrelated_interview(runtime):
    manager,access,clock=authorized(runtime)
    manager.submit_synthetic(access,events(manager,access));clock[0]=122
    assert manager.view(access,recruiter=True)['suggestion'] is None
    another=replace(access,interview=uuid4());manager.prepare(another)
    manager.invalidate(another.interview)
    assert manager.view(access)['status']=='authorized'
    manager.runs[access.interview].busy=True
    with pytest.raises(Unavailable):manager.submit_synthetic(access,events(manager,access,2))


@pytest.fixture
def api(monkeypatch,invitation_workspace):
    db,users,password,job,interview,calls,removed=invitation_workspace
    job.confirmed_snapshot={'job_reference':job.job_reference,'job_title':'Synthetic interview',
        'criteria_confirmed':True,'criteria':[{'criterion_id':'python','category':'skill','description':'Python','is_hard':True}]}
    manager=Delivery()
    monkeypatch.setattr(route,'delivery',manager)
    monkeypatch.setattr(settings,'interview_copilot_enabled',True)
    return db,users,password,job,interview,manager


async def setup(api,owner,candidate):
    db,users,password,job,interview,manager=api
    await login(owner,users[0],password)
    root=f'/api/v1/jobs/{job.id}/interviews/{interview.id}'
    raw=(await owner.post(root+'/invitation',json={})).json()['token']
    assert (await candidate.post('/api/v1/interview-access/exchange',json={'token':raw})).status_code==200
    value=(await owner.post(root+'/copilot/prepare',json={})).json()
    return root+'/copilot',value


def body(value,decision='accept'):
    return {'run_id':value['run_id'],'epoch':value['epoch'],'decision':decision,'version':VERSION}


def test_routes_real_auth_candidate_isolation_mutation_protection_and_no_get_writes(api,monkeypatch):
    db,users,password,job,interview,manager=api
    async def scenario():
        async with client() as owner,client() as candidate,client() as foreign,client() as anon:
            root,value=await setup(api,owner,candidate)
            await login(foreign,users[1],password)
            assert (await anon.get(root)).status_code==401
            assert (await candidate.get(root)).status_code==401
            assert (await foreign.get(root)).status_code==404
            assert (await owner.get(root.replace(str(interview.id),str(uuid4())))).status_code==404
            assert (await owner.get(root.replace(str(job.id),str(uuid4())))).status_code==404
            assert (await candidate.post('/api/v1/interview-access/copilot/prepare',json={})).status_code==404
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=body(value),headers={'X-TalentTrace-Request':''})).status_code==403
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=body(value),headers={'Origin':'https://foreign.invalid'})).status_code==403
            assert (await owner.post(root+'/consent',json=body(value))).status_code==200
            assert (await owner.get(root)).json()['suggestion'] is None
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=body(value))).status_code==200
            run=manager.runs[interview.id]
            # Only internal tests supply recognized events. Simulate settled time.
            run.born-=6
            scope=run.access
            result=manager.submit_synthetic(scope,events(manager,scope))
            assert result['suggestion']
            view=await owner.get(root)
            assert view.headers['cache-control']=='no-store' and view.json()['suggestion']
            private=await candidate.get('/api/v1/interview-access/copilot')
            assert private.headers['cache-control']=='no-store'
            assert not {'suggestion','processing','exploration'}&private.json().keys()
            assert 'Python' not in private.text
            # Polling cannot commit/add/flush or execute DML.
            from test_recruiter_records import SessionDouble
            async def forbidden(*args,**kwargs):raise AssertionError('No writes on GET')
            monkeypatch.setattr(SessionDouble,'commit',forbidden);monkeypatch.setattr(SessionDouble,'execute',forbidden)
            monkeypatch.setattr(SessionDouble,'flush',forbidden)
            for _ in range(2):assert (await owner.get(root)).status_code==200
            current=view.json()
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=body(current,'withdraw'))).status_code==200
            assert (await owner.get(root)).json()['suggestion'] is None
            assert len(db[InterviewSchedule])==1 and len(db[JobProfile])==1
    asyncio.run(scenario())


@pytest.mark.parametrize('change',['revision','storage_withdrawal','invitation_revoked','expired','recruiter_logout'])
def test_api_rechecks_authority_on_every_poll(api,change):
    db,users,password,job,interview,manager=api
    async def scenario():
        async with client() as owner,client() as candidate:
            root,value=await setup(api,owner,candidate)
            await owner.post(root+'/consent',json=body(value));await candidate.post('/api/v1/interview-access/copilot/consent',json=body(value))
            if change=='revision':db[JobProfile][0].revision+=1
            if change=='storage_withdrawal':db[InterviewSchedule][0].transcript_storage_revoked_at=datetime.now(timezone.utc)
            if change=='invitation_revoked':db[InterviewInvitation][0].revoked=True
            if change=='expired':db[InterviewSchedule][0].scheduled_at=datetime.now(timezone.utc)-timedelta(hours=2)
            if change=='recruiter_logout':await owner.post('/api/v1/auth/logout')
            response=await owner.get(root)
            if change=='storage_withdrawal':assert response.json()['status']=='withdrawn'
            else:assert response.status_code in {401,409}
            # Candidate path also revalidates the original recruiter session.
            other=await candidate.get('/api/v1/interview-access/copilot')
            assert other.status_code in {200,401,409}
            if other.status_code==200:assert other.json()['status']!='authorized'
    asyncio.run(scenario())


def test_disabled_default_and_no_public_ingestion(api,monkeypatch):
    monkeypatch.setattr(settings,'interview_copilot_enabled',False)
    async def scenario():
        async with client() as owner,client() as candidate:
            assert (await owner.get('/api/v1/interview-copilot/config')).json()['enabled'] is False
            assert (await candidate.get('/api/v1/interview-access/copilot')).status_code==404
            assert (await candidate.post('/api/v1/interview-access/copilot/events',json={})).status_code==404
    asyncio.run(scenario())



def test_candidate_invalid_cookie_extra_identity_and_decline(api):
    async def scenario():
        async with client() as owner, client() as candidate, client() as stranger:
            root,value=await setup(api,owner,candidate)
            assert (await stranger.get('/api/v1/interview-access/copilot')).status_code==401
            forged={**body(value),'role':'recruiter','job_id':str(uuid4())}
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=forged)).status_code==422
            assert (await candidate.post('/api/v1/interview-access/copilot/consent',json=body(value,'decline'))).status_code==200
            assert (await owner.get(root)).json()['status']=='withdrawn'
            assert (await owner.post(root+'/consent',json=body(value))).status_code==409
    asyncio.run(scenario())


def test_singleton_storage_withdrawal_hook_clears_before_cleanup(monkeypatch,runtime):
    # The privacy service must fence the assistant after durable revoke, before
    # physical deletion (which may fail). Check ordering at that exact seam.
    from app.services import copilot_delivery
    from app.services.transcript_privacy import TranscriptPrivacyService
    from app.services.interview_transcripts import TranscriptError
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    manager,access,clock=authorized(runtime)
    manager.submit_synthetic(access,events(manager,access))
    monkeypatch.setattr(copilot_delivery,'delivery',manager)
    row=SimpleNamespace(recruiter_id=access.owner,transcript_storage_revoked_at=None,transcript_deletion_status='none')
    order=[]
    @asynccontextmanager
    async def tx(factory):
        yield object()
        order.append('committed')
    import app.services.transcript_privacy as privacy
    monkeypatch.setattr(privacy,'transaction',tx)
    service=TranscriptPrivacyService(SimpleNamespace(factory=object(),clock=lambda:datetime.now(timezone.utc)))
    async def identity(*args):return row
    async def deletion(*args):
        assert order==['committed']
        assert manager.view(access,recruiter=True)['suggestion'] is None
        assert not manager.view(access)['recruiter_consented']
        raise TranscriptError('transcript_delete_failed')
    async def status(*args):return {'withdrawn':True,'deletion_status':'failed'}
    monkeypatch.setattr(service,'_identity',identity);monkeypatch.setattr(service,'delete_revoked',deletion);monkeypatch.setattr(service,'status',status)
    result=asyncio.run(service.withdraw(object(),access.interview))
    assert result['deletion_status']=='failed' and manager.view(access)['status']=='withdrawn'


def test_no_f4_shared_broadcast_or_public_capture_hook_and_capacity(runtime):
    from pathlib import Path
    source=Path('app/api/routers/interview_captions.py').read_text(encoding='utf-8')
    assert 'copilot' not in source
    manager,access,clock=runtime
    for _ in range(31):manager.prepare(replace(access,interview=uuid4()))
    with pytest.raises(Unavailable):manager.prepare(replace(access,interview=uuid4()))
    assert len(manager.runs)==32
    manager.clear();assert not manager.runs
