"""Synthetic route authorization and snapshot acknowledgement; no live database."""
import asyncio
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.models.recruiter import JobProfile
from app.api.routers import application_notifications as route
from app.services import application_notifications as service
from test_recruiter_records import workspace, client, login


def test_routes_enforce_real_auth_and_job_ownership(workspace, monkeypatch):
    db, users, password = workspace
    job = JobProfile(id=uuid4(), recruiter_id=users[0].id, job_reference='TT-JOB-'+'A'*16,
                     job_title='Synthetic', revision=1, suggestions={}, sources=[], scoring_weights={})
    db[JobProfile] = [job]
    calls=[]
    async def discover(session, selected, root):
        calls.append(selected.id)
        return dict(job_id=selected.id,received_count=0,new_count=0,unavailable_count=0,invalid_batch_count=0,applications=[])
    async def mark(*args):calls.append('mark')
    monkeypatch.setattr(route,'discover',discover)
    monkeypatch.setattr(route,'mark_viewed',mark)
    monkeypatch.setattr(route,'private_settings',lambda request:N(cv_upload_root=Path('unused')))
    async def run():
        path=f'/api/v1/jobs/{job.id}/applications'
        async with client() as owner, client() as foreign, client() as anonymous:
            assert (await anonymous.get(path)).status_code==401
            assert (await anonymous.post(path+'/viewed',json={'applications':[]})).status_code==401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            assert (await foreign.get(path)).status_code==404
            assert (await foreign.post(path+'/viewed',json={'applications':[]})).status_code==404
            assert not calls
            assert (await owner.get(path)).json()['received_count']==0
            assert (await owner.post(path+'/viewed',json={'applications':[]})).status_code==204
            assert (await owner.post(path+'/viewed',json={'applications':[]},headers={'X-TalentTrace-Request':'0'})).status_code==403
    asyncio.run(run())
    assert calls==[job.id,'mark']


def test_late_arrival_and_repeat_acknowledgement_write_only_snapshot(monkeypatch):
    first,late=(uuid4(),uuid4()),(uuid4(),uuid4())
    job=N(id=uuid4());viewed=set()
    async def discover(*args):return {'applications':[dict(batch_id=k[0],upload_id=k[1]) for k in (first,late)]}
    monkeypatch.setattr(service,'discover',discover)
    class Session:
        async def execute(self,statement):
            params=statement.compile().params
            viewed.add((params['batch_id_m0'],params['upload_id_m0']))
        async def commit(self):pass
    async def run():
        for _ in range(2):await service.mark_viewed(Session(),job,Path('unused'),[N(batch_id=first[0],upload_id=first[1])])
    asyncio.run(run())
    assert viewed=={first} and late not in viewed


def test_existing_migration_chain_has_single_compatible_head():
    scripts=ScriptDirectory.from_config(Config('alembic.ini'))
    assert scripts.get_heads()==['0017_booked_interview_email']
    assert scripts.get_revision('0011_application_views').down_revision=='0010_interview_transcripts'


def test_owned_analytics_and_mocked_publication_coexist(workspace, monkeypatch):
    """Real auth/routes; notification state and publisher are synthetic doubles."""
    from test_recruiter_records import install_chat
    from test_recruiter_chat import MESSAGE
    from app.api.routers import recruiter_chat
    from app.schemas.job_publication import PublicationResult
    _, users, password = workspace
    install_chat(monkeypatch)
    identity=(uuid4(),uuid4()); viewed=set(); published=[]
    async def discover(session, job, root):
        return dict(job_id=job.id,received_count=1,new_count=int(identity not in viewed),
            unavailable_count=0,invalid_batch_count=0,applications=[dict(batch_id=identity[0],
            upload_id=identity[1],origin='native_storage',available=True,is_new=identity not in viewed)])
    async def mark(session, job, root, rows):viewed.update((r.batch_id,r.upload_id) for r in rows)
    class Publisher:
        async def publish(self, request):
            published.append(request.mcp_job())
            return PublicationResult(destination='discord',status='published',external_id='123456789012345678')
    monkeypatch.setattr(route,'discover',discover);monkeypatch.setattr(route,'mark_viewed',mark)
    monkeypatch.setattr(route,'private_settings',lambda request:N(cv_upload_root=Path('unused')))
    monkeypatch.setattr(recruiter_chat,'get_job_publisher',Publisher)
    monkeypatch.setattr(recruiter_chat,'publication_attempts',{})
    async def run():
        async with client() as owner,client() as foreign:
            await login(owner,users[0],password);await login(foreign,users[1],password)
            reply=(await owner.post('/api/v1/recruiter-chat',json={'message':MESSAGE})).json()
            path=f'/api/v1/jobs/{reply["draft_id"]}/applications'
            assert (await owner.get(path)).json()['new_count']==1 and not viewed
            assert (await foreign.get(path)).status_code==404
            assert (await foreign.post(path+'/viewed',json={'applications':[]})).status_code==404
            assert (await owner.post(path+'/viewed',json={'applications':[dict(batch_id=str(identity[0]),upload_id=str(identity[1]))]})).status_code==204
            draft=reply['job_description_result']['job_description']
            payload={k:v for k,v in draft.items() if k!='policy_citation_ids'};payload['job_id']=reply['draft_id']
            assert (await foreign.post('/api/v1/recruiter-chat/publish',json=payload)).status_code==404
            for _ in range(2):
                result=await owner.post('/api/v1/recruiter-chat/publish',json=payload)
                assert result.status_code==200 and result.json()['status']=='published'
            assert len(published)==1 and published[0]['job_reference']==reply['job_reference']
            counts=(await owner.get(path)).json();assert counts['received_count']==1 and counts['new_count']==0
    asyncio.run(run())
