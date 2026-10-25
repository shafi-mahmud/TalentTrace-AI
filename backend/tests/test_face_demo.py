"""Synthetic vectors/SQL doubles only. No face images, capture, model or Cloud calls."""
import asyncio
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import pytest
from fastapi import HTTPException
from app.services.face_demo import Binding,FaceDemoStore,similarity,synthetic_vector
from app.api.routers import face_demo as route
from app.core.config import settings,Settings
from app.db.models.recruiter import InterviewInvitation,InterviewSchedule,JobProfile
from test_interview_access import invitation_workspace
from test_recruiter_records import workspace,client,login


def scope():return Binding(*(uuid4() for _ in range(6)),session_digest='synthetic-digest',criteria_revision=1)


def test_actual_numeric_comparison_and_explicit_nonidentity_output():
    same=similarity(synthetic_vector('vector-a-reference'),synthetic_vector('vector-a-probe'))
    different=similarity(synthetic_vector('vector-a-reference'),synthetic_vector('vector-b-probe'))
    assert same['assessment']=='above_demo_threshold' and same['similarity']>.99
    assert different['assessment']=='below_demo_threshold' and different['similarity']<.02
    for result in (same,different):
        assert result['mode']=='simulated_vectors' and result['model_used'] is None
        assert not result['identity_verified'] and not result['liveness_checked']
    with pytest.raises(HTTPException):synthetic_vector('/private/image.png')
    with pytest.raises(ValueError):similarity([float('nan')]*128,[1]*128)
    with pytest.raises(ValueError):similarity([0]*128,[1]*128)


def test_store_requires_consent_and_reference_and_cleans_on_withdrawal():
    async def run():
        store=FaceDemoStore();a=scope();n=uuid4()
        with pytest.raises(HTTPException):store.enroll(a,n,'vector-a-reference')
        n=UUID(store.consent(a)['run_id'])
        with pytest.raises(HTTPException):store.compare(a,n,'vector-a-probe')
        store.enroll(a,n,'vector-a-reference');reference=store.entries[a.interview_id].reference
        with pytest.raises(HTTPException):store.enroll(a,n,'vector-b-reference')
        assert store.compare(a,n,'vector-a-probe')['assessment']=='above_demo_threshold'
        store.remove(a.interview_id,n)
        assert not store.entries and all(v==0 for v in reference)
        with pytest.raises(HTTPException):store.compare(a,n,'vector-a-probe')
        fresh=UUID(store.consent(a)['run_id']);store.remove(a.interview_id,n)
        assert store.checked(a,fresh)
        store.clear()
    asyncio.run(run())

@pytest.mark.parametrize('field,value',[('job_id',uuid4()),('upload_id',uuid4()),('batch_id',uuid4()),('recruiter_id',uuid4()),('criteria_revision',9),('invitation_id',uuid4()),('session_digest','rotated')])
def test_exact_binding_change_restricts_and_removes_reference(field,value):
    async def run():
        store=FaceDemoStore();a=scope();n=UUID(store.consent(a)['run_id'])
        store.enroll(a,n,'vector-a-reference')
        with pytest.raises(HTTPException):store.checked(replace(a,**{field:value}),n)
        assert not store.entries
    asyncio.run(run())


def test_fixed_expiry_capacity_and_other_interview_survives():
    async def run():
        clock=[0.];store=FaceDemoStore(lambda:clock[0]);a,b=scope(),scope()
        n=UUID(store.consent(a)['run_id']);m=UUID(store.consent(b)['run_id'])
        store.enroll(a,n,'vector-a-reference');store.enroll(b,m,'vector-b-reference')
        store.remove(a.interview_id,n);assert store.view(b,m)['state']=='enrolled'
        clock[0]=299;store.compare(b,m,'vector-b-probe')
        clock[0]=301
        with pytest.raises(HTTPException):store.checked(b,m)
        assert not store.entries
        for _ in range(16):store.consent(scope())
        with pytest.raises(HTTPException):store.consent(scope())
        store.clear()
    asyncio.run(run())


@pytest.fixture
def configured(invitation_workspace,monkeypatch):
    db,users,password,job,interview,*_=invitation_workspace
    monkeypatch.setattr(route,'store',FaceDemoStore())
    monkeypatch.setattr(settings,'face_synthetic_demo_enabled',True)
    monkeypatch.setattr(settings,'face_synthetic_demo_interview_ids',[interview.id])
    yield db,users,password,job,interview
    route.store.clear()


async def participants(owner,candidate,users,password,job,interview):
    await login(owner,users[0],password)
    raw=(await owner.post(f'/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation',json={})).json()['token']
    assert (await candidate.post('/api/v1/interview-access/exchange',json={'token':raw})).status_code==200


def test_authenticated_candidate_consent_recruiter_only_enroll_compare_and_withdraw(configured):
    _,users,password,job,interview=configured
    async def run():
        async with client() as owner,client() as candidate,client() as foreign,client() as anonymous:
            await participants(owner,candidate,users,password,job,interview);await login(foreign,users[1],password)
            base=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-demo'
            consent='/api/v1/interview-access/face-demo/consent'
            assert (await anonymous.post(consent,json={'version':route.CONSENT_VERSION,'decision':'accept'})).status_code==401
            info=(await candidate.get(consent)).json()
            assert info['real_biometrics_enabled'] is False and 'manual' in info['wording']
            assert (await candidate.post(consent,json={'version':'caption-v1','decision':'accept'})).status_code==422
            r=await candidate.post(consent,json={'version':route.CONSENT_VERSION,'decision':'accept'})
            assert r.status_code==200;run_id=r.json()['run_id']
            body={'run_id':run_id,'review_confirmed':True,'fixture':'vector-a-reference'}
            assert (await owner.post(f'/api/v1/jobs/{uuid4()}/interviews/{interview.id}/face-demo/enroll',json=body)).status_code==404
            assert (await foreign.post(base+'/enroll',json=body)).status_code==404
            assert (await candidate.post(base+'/enroll',json=body)).status_code==401
            assert (await owner.post(base+'/enroll',json={**body,'review_confirmed':False})).status_code==422
            assert (await owner.post(base+'/enroll',json={**body,'review_confirmed':1})).status_code==422
            assert (await owner.post(base+'/enroll',json={**body,'image':'PRIVATE'})).status_code==422
            assert (await owner.post(base+'/enroll',json={**body,'fixture':'/private/face.png'})).status_code==422
            assert (await owner.post(base+'/enroll',json=body)).status_code==200
            for fixture,assessment in [('vector-a-probe','above_demo_threshold'),('vector-b-probe','below_demo_threshold')]:
                result=await owner.post(base+'/compare',json={**body,'fixture':fixture})
                assert result.status_code==200 and result.json()['assessment']==assessment
                assert result.headers['cache-control']=='no-store'
            assert (await candidate.get(base+'/'+run_id)).status_code==401
            assert (await foreign.get(base+'/'+run_id)).status_code==404
            assert (await owner.get(base+'/'+run_id)).json()['state']=='compared'
            assert (await candidate.post('/api/v1/interview-access/face-demo/withdraw',json={'run_id':run_id})).status_code==200
            assert (await owner.get(base+'/'+run_id)).status_code==409
            assert not route.store.entries
    asyncio.run(run())

@pytest.mark.parametrize('failure',['revoked','expired','criteria','disabled','allowlist','session','deleted'])
def test_access_changes_restrict_result_and_cleanup_is_bounded(configured,monkeypatch,failure):
    db,users,password,job,interview=configured
    async def run():
        async with client() as owner,client() as candidate:
            await participants(owner,candidate,users,password,job,interview)
            n=(await candidate.post('/api/v1/interview-access/face-demo/consent',json={'version':route.CONSENT_VERSION,'decision':'accept'})).json()['run_id']
            base=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-demo'
            assert (await owner.post(base+'/enroll',json={'run_id':n,'review_confirmed':True,'fixture':'vector-a-reference'})).status_code==200
            if failure=='revoked':db[InterviewInvitation][0].revoked=True
            if failure=='expired':db[InterviewInvitation][0].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            if failure=='criteria':db[JobProfile][0].revision+=1
            if failure=='disabled':monkeypatch.setattr(settings,'face_synthetic_demo_enabled',False)
            if failure=='allowlist':monkeypatch.setattr(settings,'face_synthetic_demo_interview_ids',[])
            if failure=='session':db[InterviewInvitation][0].candidate_session_hash='rotated'
            if failure=='deleted':db[InterviewSchedule]=[]
            response=await owner.get(base+'/'+n)
            assert response.status_code in {404,409}
            if failure in {'revoked','expired','disabled','session'}:assert not route.store.entries
            # Missing/changed authority never returns data; remaining RAM expires within five minutes.
    asyncio.run(run())


def test_defaults_cannot_collect_faces():
    assert not Settings(_env_file=None).face_synthetic_demo_enabled
    assert Settings(_env_file=None).face_synthetic_demo_interview_ids==[]
    schema=route.Enrollment.model_json_schema()
    assert set(schema['properties'])=={'run_id','review_confirmed','fixture'}
