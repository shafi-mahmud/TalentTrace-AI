"""Encrypted synthetic references; real routes/auth, SQL doubles and fake feature worker."""
import asyncio,base64,os
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from app.services.face_vault import FaceVault,VaultError,VERSION
from app.services.face_demo import Binding,synthetic_vector
from app.api.routers import face_workflow as route
from app.services import face_workflow as runtime
from app.core.config import settings,Settings
from app.db.models.recruiter import InterviewInvitation,InterviewSchedule
from test_interview_access import invitation_workspace
from test_recruiter_records import workspace,client,login


def scope():return Binding(*(uuid4() for _ in range(6)),session_digest='synthetic-session',criteria_revision=1)
def key():return base64.urlsafe_b64encode(os.urandom(32)).decode()
def vector():return list(synthetic_vector('vector-a-reference'))


def test_encrypted_restart_expiry_and_no_plaintext(tmp_path):
    clock=[1000];k=key();a=scope();v=FaceVault(tmp_path,k,60,lambda:clock[0]);consent=v.consent(a,'a')
    v.enroll(a,consent['run_id'],vector(),{'source':'synthetic'})
    ciphertext=v.path(a.interview_id).read_bytes()
    for secret in (str(a.job_id),'feature','synthetic-session',consent['withdrawal_receipt']):assert secret.encode() not in ciphertext
    restarted=FaceVault(tmp_path,k,60,lambda:clock[0])
    assert restarted.compare(a,consent['run_id'],vector())['similarity']==1
    assert restarted.read(a)['audit'][-1]['event']=='compared'
    clock[0]=1061
    with pytest.raises(VaultError,match='expired'):restarted.read(a)
    assert not restarted.path(a.interview_id).exists()

@pytest.mark.parametrize('change',[{'job_id':uuid4()},{'upload_id':uuid4()},{'recruiter_id':uuid4()},{'session_digest':'other'},{'criteria_revision':2}])
def test_wrong_binding_fails_closed_without_deleting_unrelated(tmp_path,change):
    v=FaceVault(tmp_path,key(),60);a=scope();c=v.consent(a,'a');v.enroll(a,c['run_id'],vector(),{})
    with pytest.raises(VaultError,match='source_changed'):v.read(replace(a,**change))
    assert v.read(a)['state']=='enrolled'


def test_withdrawal_cas_tampering_rotation_and_cleanup(tmp_path):
    k=key();v=FaceVault(tmp_path,k,60);a=scope();c=v.consent(a,'a')
    with pytest.raises(VaultError):v.withdraw(a.interview_id,'wrong')
    v.withdraw(a.interview_id,c['withdrawal_receipt'])
    with pytest.raises(VaultError,match='withdrawn'):v.enroll(a,c['run_id'],vector(),{})
    fresh=FaceVault(tmp_path,k,60)
    with pytest.raises(VaultError,match='withdrawn'):fresh.read(a)
    fresh.delete(a.interview_id);new=fresh.consent(a,'a')
    with pytest.raises(VaultError,match='run_changed'):fresh.enroll(a,c['run_id'],vector(),{})
    with pytest.raises(VaultError):FaceVault(tmp_path,key(),60).read(a)
    p=fresh.path(a.interview_id);data=p.read_bytes();p.write_bytes(data[:-1]+bytes([data[-1]^1]))
    with pytest.raises(VaultError,match='restricted'):fresh.read(a)
    fresh.delete(a.interview_id)
    assert not list(tmp_path.glob('*.sealed'))


def test_expiry_cleanup_and_private_permissions(tmp_path):
    clock=[100];v=FaceVault(tmp_path,key(),60,lambda:clock[0]);a=scope();v.consent(a,'a')
    clock[0]=161;v.cleanup();assert not list(tmp_path.glob('*.sealed'))
    tmp_path.chmod(0o755)
    with pytest.raises(VaultError):FaceVault(tmp_path,key(),60)
    tmp_path.chmod(0o700)

@pytest.fixture
def configured(invitation_workspace,tmp_path,monkeypatch):
    db,users,password,job,interview,*_=invitation_workspace
    store=FaceVault(tmp_path,key(),3600)
    monkeypatch.setattr(settings,'face_workflow_enabled',True)
    monkeypatch.setattr(settings,'face_workflow_synthetic_identities',{interview.id:'a'})
    monkeypatch.setattr(settings,'face_workflow_viva_interview_ids',[interview.id])
    monkeypatch.setattr(runtime,'vault',lambda require_enabled=True:store)
    async def feature(identity,probe):return {'feature':vector(),'provenance':{'source':'server_generated_geometry','identity':identity}}
    monkeypatch.setattr(runtime,'feature',feature)
    return db,users,password,job,interview,store

async def enroll_flow(owner,candidate,users,password,job,interview):
    await login(owner,users[0],password)
    raw=(await owner.post(f'/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation',json={})).json()['token']
    assert (await candidate.post('/api/v1/interview-access/exchange',json={'token':raw})).status_code==200
    c=await candidate.post('/api/v1/interview-access/face-workflow/consent',json={'version':VERSION,'accepted':True})
    assert c.status_code==200
    return c.json()


def test_online_enrollment_restart_and_later_recruiter_only_viva(configured,monkeypatch):
    db,users,password,job,interview,store=configured
    async def run():
        async with client() as owner,client() as candidate,client() as other:
            c=await enroll_flow(owner,candidate,users,password,job,interview);await login(other,users[1],password)
            base=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-workflow'
            assert (await candidate.post('/api/v1/interview-access/face-workflow/enroll',json={'run_id':c['run_id']})).status_code==200
            monkeypatch.setattr(runtime,'vault',lambda require_enabled=True:FaceVault(store.root,base64.urlsafe_b64encode(b'x'*32).decode(),3600))
            assert (await owner.get(base)).status_code==409 # wrong restart key cannot fabricate a new reference
            monkeypatch.setattr(runtime,'vault',lambda require_enabled=True:store)
            db[InterviewSchedule][0].scheduled_at=datetime.now(timezone.utc)-timedelta(days=1)
            db[InterviewInvitation][0].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            body={'run_id':c['run_id'],'sample':'same-design','human_review_confirmed':True}
            assert (await candidate.post(base+'/verify',json=body)).status_code==401
            assert (await other.post(base+'/verify',json=body)).status_code==404
            assert (await owner.post(base+'/verify',json={**body,'image':'PRIVATE'})).status_code==422
            assert (await owner.post(base+'/verify',json={**body,'human_review_confirmed':False})).status_code==422
            result=await owner.post(base+'/verify',json=body)
            assert result.status_code==200 and result.json()['provisional'] and not result.json()['identity_verified']
            assert result.headers['cache-control']=='no-store'
            assert (await candidate.post('/api/v1/face-workflow/withdraw',json={'interview_id':str(interview.id),'receipt':c['withdrawal_receipt']})).status_code==200
            assert (await owner.post(base+'/verify',json=body)).status_code==409
            assert (await owner.post(base+'/delete',json={})).status_code==200
            assert not list(store.root.glob('*.sealed'))
    asyncio.run(run())


def test_withdrawal_during_inference_cannot_resurrect_reference(configured,monkeypatch):
    _,users,password,job,interview,store=configured
    # Check the actual record rather than any supplied client identity.
    async def scenario():
        async with client() as owner,client() as candidate:
            c=await enroll_flow(owner,candidate,users,password,job,interview)
            async def delayed(identity,probe):
                store.withdraw(interview.id,c['withdrawal_receipt']);return {'feature':vector(),'provenance':{}}
            monkeypatch.setattr(runtime,'feature',delayed)
            response=await candidate.post('/api/v1/interview-access/face-workflow/enroll',json={'run_id':c['run_id']})
            assert response.status_code==409
            with store.locked():assert store._load(interview.id)['feature'] is None
    asyncio.run(scenario())

@pytest.mark.parametrize('failure',['revoke','rotation','viva_permission','criteria','disable'])
def test_revocation_and_authorization_restrict_viva(configured,monkeypatch,failure):
    db,users,password,job,interview,store=configured
    async def run():
        async with client() as owner,client() as candidate:
            c=await enroll_flow(owner,candidate,users,password,job,interview)
            assert (await candidate.post('/api/v1/interview-access/face-workflow/enroll',json={'run_id':c['run_id']})).status_code==200
            if failure=='revoke':db[InterviewInvitation][0].revoked=True
            if failure=='rotation':db[InterviewInvitation][0].candidate_session_hash='changed'
            if failure=='viva_permission':monkeypatch.setattr(settings,'face_workflow_viva_interview_ids',[])
            if failure=='criteria':db[type(job)][0].revision+=1
            if failure=='disable':monkeypatch.setattr(settings,'face_workflow_enabled',False)
            response=await owner.post(f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-workflow/verify',json={'run_id':c['run_id'],'sample':'same-design','human_review_confirmed':True})
            assert response.status_code in (403,404,409)
    asyncio.run(run())


def test_default_off_and_no_automatic_retention():
    c=Settings(_env_file=None)
    assert not c.face_workflow_enabled and c.face_workflow_retention_seconds is None
    assert not c.face_workflow_synthetic_identities and not c.face_workflow_viva_interview_ids


def test_new_python_process_reads_encrypted_synthetic_reference(tmp_path):
    import json,subprocess,sys
    from app.services.face_vault import scope_dict
    k=key();v=FaceVault(tmp_path,k,60);a=scope();c=v.consent(a,'a');v.enroll(a,c['run_id'],vector(),{})
    script="""import json,sys
from app.services.face_vault import FaceVault
from app.services.face_demo import Binding
v=json.load(sys.stdin)
row=FaceVault(v['root'],v['key'],60).read(Binding(**v['scope']))
print(row['state'])
"""
    result=subprocess.run([sys.executable,'-B','-c',script],input=json.dumps({'root':str(tmp_path),'key':k,'scope':scope_dict(a)}),
        text=True,capture_output=True,timeout=10,env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).resolve().parents[1])})
    assert result.returncode==0 and result.stdout.strip()=='enrolled'
    assert k not in result.stdout and not result.stderr


def test_failed_worker_is_killed_and_temporary_tree_removed(tmp_path,monkeypatch):
    store=FaceVault(tmp_path,key(),60);monkeypatch.setattr(runtime,'vault',lambda:store)
    monkeypatch.setattr(settings,'face_workflow_enabled',True)
    monkeypatch.setattr(settings,'face_workflow_python',Path('/synthetic/python'))
    monkeypatch.setattr(settings,'face_workflow_models',tmp_path)
    class Process:
        returncode=None
        async def communicate(self,data):raise TimeoutError()
        def kill(self):self.returncode=-9
        async def wait(self):return self.returncode
    process=Process()
    async def start(*args,**kwargs):
        assert 'GROQ_API_KEY' not in kwargs['env'] and 'FACE_WORKFLOW_KEY' not in kwargs['env']
        return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',start)
    with pytest.raises(VaultError,match='sample_unavailable'):asyncio.run(runtime.feature('a',False))
    assert process.returncode==-9 and not list(tmp_path.glob('worker-*'))


def test_actual_models_restart_safe_enrollment_and_provisional_viva(monkeypatch):
    if os.environ.get('TT_FACE_ACTUAL_MODEL_TEST')!='1':pytest.skip('Explicit local-model gate')
    from tempfile import TemporaryDirectory
    from app.core.config import REPOSITORY_ROOT
    python=REPOSITORY_ROOT/'data/face-cpu-20261026/venv/bin/python'
    models=REPOSITORY_ROOT/'data/face-cpu-20261026/models'
    if not python.is_file() or not models.is_dir():pytest.skip('Approved local runtime/models unavailable')
    with TemporaryDirectory(prefix='face-workflow-test-',dir=REPOSITORY_ROOT/'data') as directory:
        root=Path(directory);k=key();a=scope();v=FaceVault(root,k,600)
        monkeypatch.setattr(settings,'face_workflow_enabled',True)
        monkeypatch.setattr(settings,'face_workflow_root',root)
        from pydantic import SecretStr
        monkeypatch.setattr(settings,'face_workflow_key',SecretStr(k))
        monkeypatch.setattr(settings,'face_workflow_retention_seconds',600)
        monkeypatch.setattr(settings,'face_workflow_python',python)
        monkeypatch.setattr(settings,'face_workflow_models',models)
        async def run():
            c=v.consent(a,'a');reference=await runtime.feature('a',False)
            v.enroll(a,c['run_id'],reference['feature'],reference['provenance'])
            restarted=FaceVault(root,k,600)
            probe=await runtime.feature('a',True);same=restarted.compare(a,c['run_id'],probe['feature'])
            other=await runtime.feature('c',False);different=restarted.compare(a,c['run_id'],other['feature'])
            assert same['similarity']>.99 and same['human_review_required'] and not same['identity_verified']
            # The measured C score is high; do not assert successful identity discrimination.
            assert -1<=different['similarity']<=1 and different['decision']=='no_automated_decision'
            restarted.withdraw(a.interview_id,c['withdrawal_receipt'])
            with pytest.raises(VaultError):restarted.compare(a,c['run_id'],probe['feature'])
            restarted.delete(a.interview_id)
            assert not list(root.glob('*.sealed')) and not list(root.glob('worker-*'))
        asyncio.run(run())
    assert not root.exists()


def test_crash_temp_and_orphan_sample_cleanup_respects_expiry(tmp_path):
    clock=[1000];v=FaceVault(tmp_path,key(),60,lambda:clock[0]);a=scope();v.consent(a,'a')
    temp=tmp_path/('.'+str(a.interview_id)+'.'+'a'*16+'.tmp');temp.write_bytes(v.path(a.interview_id).read_bytes());temp.chmod(0o600)
    orphan=tmp_path/'worker-test';orphan.mkdir(mode=0o700);(orphan/'synthetic.png').write_bytes(b'synthetic only')
    os.utime(orphan,(900,900));v.cleanup()
    assert temp.exists() and not orphan.exists()
    clock[0]=1061;v.cleanup();assert not temp.exists() and not v.path(a.interview_id).exists()


def test_cancelled_worker_cannot_outlive_cleanup(tmp_path,monkeypatch):
    store=FaceVault(tmp_path,key(),60);monkeypatch.setattr(runtime,'vault',lambda:store)
    monkeypatch.setattr(settings,'face_workflow_enabled',True)
    monkeypatch.setattr(settings,'face_workflow_python',Path('/synthetic/python'));monkeypatch.setattr(settings,'face_workflow_models',tmp_path)
    async def run():
        entered=asyncio.Event()
        class Process:
            returncode=None
            async def communicate(self,data):entered.set();await asyncio.Event().wait()
            def kill(self):self.returncode=-9
            async def wait(self):return self.returncode
        process=Process()
        async def start(*args,**kwargs):return process
        monkeypatch.setattr(asyncio,'create_subprocess_exec',start)
        task=asyncio.create_task(runtime.feature('a',False));await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert process.returncode==-9 and not list(tmp_path.glob('worker-*'))
    asyncio.run(run())


def test_actual_model_authenticated_online_to_viva_http(configured,monkeypatch):
    if os.environ.get('TT_FACE_ACTUAL_MODEL_TEST')!='1':pytest.skip('Explicit actual model gate')
    from tempfile import TemporaryDirectory
    from app.core.config import REPOSITORY_ROOT
    from pydantic import SecretStr
    import importlib.util
    spec=importlib.util.spec_from_file_location('actual_face_worker_runtime',Path(runtime.__file__))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    _,users,password,job,interview,_=configured
    with TemporaryDirectory(prefix='face-http-test-',dir=REPOSITORY_ROOT/'data') as directory:
        root=Path(directory);k=key()
        monkeypatch.setattr(settings,'face_workflow_root',root);monkeypatch.setattr(settings,'face_workflow_key',SecretStr(k))
        monkeypatch.setattr(settings,'face_workflow_retention_seconds',600)
        monkeypatch.setattr(settings,'face_workflow_python',REPOSITORY_ROOT/'data/face-cpu-20261026/venv/bin/python')
        monkeypatch.setattr(settings,'face_workflow_models',REPOSITORY_ROOT/'data/face-cpu-20261026/models')
        monkeypatch.setattr(runtime,'vault',lambda require_enabled=True:FaceVault(root,k,600))
        monkeypatch.setattr(runtime,'feature',module.feature)
        async def run():
            async with client() as owner,client() as candidate:
                c=await enroll_flow(owner,candidate,users,password,job,interview)
                enrolled=await candidate.post('/api/v1/interview-access/face-workflow/enroll',json={'run_id':c['run_id']})
                assert enrolled.status_code==200 and enrolled.json()['state']=='enrolled'
                base=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-workflow'
                assert (await owner.get(base)).json()['state']=='enrolled'
                response=await owner.post(base+'/verify',json={'run_id':c['run_id'],'sample':'same-design','human_review_confirmed':True})
                assert response.status_code==200 and response.json()['similarity']>.99 and not response.json()['identity_verified']
                withdrawn=await candidate.post('/api/v1/face-workflow/withdraw',json={'interview_id':str(interview.id),'receipt':c['withdrawal_receipt']})
                assert withdrawn.status_code==200
                assert (await owner.get(base)).json()['state']=='withdrawn'
                assert (await owner.post(base+'/delete',json={})).status_code==200
                assert not list(root.glob('*.sealed')) and not list(root.glob('worker-*'))
        asyncio.run(run())
    assert not root.exists()


def test_authenticated_candidate_can_withdraw_after_browser_reload_without_receipt(configured):
    _,users,password,job,interview,store=configured
    async def run():
        async with client() as owner,client() as candidate:
            c=await enroll_flow(owner,candidate,users,password,job,interview)
            assert (await candidate.post('/api/v1/interview-access/face-workflow/enroll',json={'run_id':c['run_id']})).status_code==200
            restored=(await candidate.get('/api/v1/interview-access/face-workflow')).json()
            assert 'withdrawal_receipt' not in restored
            response=await candidate.post('/api/v1/interview-access/face-workflow/withdraw',json={'run_id':restored['run_id']})
            assert response.status_code==200
            assert (await owner.get(f'/api/v1/jobs/{job.id}/interviews/{interview.id}/face-workflow')).json()['state']=='withdrawn'
    asyncio.run(run())
