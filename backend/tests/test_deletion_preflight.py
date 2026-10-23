"""No maintenance actions: pure decisions plus disposable PostgreSQL observations."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services.candidate_inventory import Target
from app.services.deletion_preflight import (
    assess, database_observations, manifest, preflight, runtime_observations, storage_observations,
)
from test_candidate_inventory import postgres  # existing opt-in disposable fixture


RUNTIME = dict(visibility='unknown', known_processes={}, target_access='unknown')


def test_no_processes_never_proves_maintenance():
    db = dict(status='observed', other_connections=0, open_transactions=0,
              prepared_transactions=0, full_activity_visibility=True, hidden_states=0,
              administration_capability='superuser')
    result = assess(db, dict(status='observed'), RUNTIME, True)
    assert result['state']=='blocked' and result['deletion_ready'] is False
    assert 'independent_writers_not_excluded' in result['blockers']
    assert 'durable_restart_block_unavailable' in result['blockers']
    assert assess(dict(status='unknown'), dict(status='unknown',reason='unavailable'), RUNTIME, False)['state']=='unknown'


def test_storage_missing_and_unsafe(tmp_path, monkeypatch):
    assert storage_observations(tmp_path/'absent')['status']=='blocked'
    assert storage_observations(tmp_path)['exclusivity']=='not_established'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p==tmp_path or original(p))
    assert storage_observations(tmp_path)['reason']=='unsafe_storage_root'


def test_process_hints_sanitized_and_incomplete(monkeypatch):
    processes = [SimpleNamespace(pid=123456,info=dict(name='python',cmdline=['TalentTrace', 'PASSWORD_SHOULD_NOT_APPEAR'])),
                 SimpleNamespace(pid=123457,info=dict(name='python',cmdline=['independent_writer']))]
    monkeypatch.setitem(sys.modules, 'psutil', SimpleNamespace(process_iter=lambda fields: processes,
        AccessDenied=PermissionError, NoSuchProcess=ProcessLookupError))
    monkeypatch.setattr('app.services.deletion_preflight.subprocess.run',
                        lambda *a, **k: SimpleNamespace(returncode=1))
    observed = runtime_observations()
    assert observed['known_processes']['backend_or_cli']==1
    assert observed['other_python_processes']==1
    assert observed['target_access']=='unknown' and observed['scheduled_launchers']=='unknown'
    assert 'PASSWORD_SHOULD_NOT_APPEAR' not in json.dumps(observed)


def test_manifest_canonical_and_no_authorization():
    target=Target(uuid4(),uuid4(),uuid4(),uuid4())
    observation=dict(categories={'cv_files':dict(status='missing',count=0,reason='cv_file_missing'),
        'screening_versions':dict(status='confirmed',count=2,reason='exact_association')},
        blockers=['z','a'], limitations=['b','a'])
    first=manifest(target,observation)
    reordered=dict(observation,categories=dict(reversed(list(observation['categories'].items()))),blockers=['a','z'])
    assert first==manifest(target,reordered)
    assert first['plan']['deletion_authorized'] is False
    assert first['plan']['candidate_wide_deletion_resolved'] is False


def test_unavailable_database(tmp_path):
    async def scenario():
        engine=create_async_engine('postgresql+asyncpg://unused:unused@127.0.0.1:1/unavailable',connect_args={'timeout':.2},hide_parameters=True)
        try:
            result=await preflight(async_sessionmaker(engine),Target(uuid4(),uuid4(),uuid4(),uuid4()),tmp_path,runtime=RUNTIME)
            assert result['preflight']['state']=='unknown'
            assert result['manifest']['status']=='unavailable'
            assert 'unused' not in json.dumps(result)
        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_postgres_connections_scope_manifest_and_no_mutation(postgres,tmp_path):
    async def scenario():
        engine=create_async_engine(postgres,hide_parameters=True)
        factory=async_sessionmaker(engine)
        target=Target(uuid4(),uuid4(),uuid4(),uuid4())
        ref='TT-JOB-'+uuid4().hex[:16].upper()
        directory=tmp_path/str(target.recruiter_id)/ref/str(target.batch_id)
        directory.mkdir(parents=True)
        cv=directory/(str(target.upload_id)+'.pdf');cv.write_bytes(b'fictional-test-data')
        other=directory/(str(uuid4())+'.pdf');other.write_bytes(b'preserve-other-applicant')
        role='n19_limited_'+uuid4().hex[:10]
        try:
            async with factory.begin() as db:
                await db.execute(text("INSERT INTO recruiters(id,email,password_hash,active) VALUES (:id,'fictional-preflight@example.test','unused',true)"),dict(id=target.recruiter_id))
                await db.execute(text("""INSERT INTO job_profiles(id,recruiter_id,job_reference,job_title,revision,sources,suggestions,scoring_weights)
                    VALUES (:job_id,:recruiter_id,:ref,'Synthetic',2,'[]','{}',:weights)"""),
                    dict(target.parameters(),ref=ref,weights=json.dumps(dict(skill=100,experience=0,education=0))))
                for upload in [target.upload_id,uuid4()]:
                    await db.execute(text("""INSERT INTO candidate_scores(id,job_id,batch_id,upload_id,criteria_revision,scoring_version,payload)
                        VALUES (:id,:job_id,:batch_id,:upload_id,2,'synthetic','{"private":"do-not-expose"}')"""),dict(target.parameters(),id=uuid4(),upload_id=upload))
                await db.execute(text(f'CREATE ROLE {role} NOLOGIN'))
            async def fingerprint():
                async with factory() as db:
                    return await db.scalar(text("SELECT md5(string_agg(row_to_json(t)::text,'' ORDER BY id)) FROM candidate_scores t"))
            before=await fingerprint();bytes_before={p.name:p.read_bytes() for p in directory.iterdir()}
            async with factory() as other_connection:
                await other_connection.execute(text('SELECT 1'))
                result=await preflight(factory,target,tmp_path,runtime=RUNTIME)
                assert result['database']['other_connections']>=1
                assert result['database']['open_transactions']>=1
                assert result['database']['database']=='n19_test'
                assert 'other_database_connections_present' in result['preflight']['blockers']
            again=await preflight(factory,target,tmp_path,runtime=RUNTIME)
            assert result['manifest']==again['manifest']
            plan=result['manifest']['plan']
            assert plan['confirmed_database_associations']['screening_versions']['count']==1
            assert plan['files']['relative_paths']==[(cv.relative_to(tmp_path)).as_posix()]
            assert 'do-not-expose' not in json.dumps(result)
            assert before==await fingerprint()
            assert bytes_before=={p.name:p.read_bytes() for p in directory.iterdir()}
            wrong=await preflight(factory,Target(uuid4(),target.job_id,target.batch_id,target.upload_id),tmp_path,runtime=RUNTIME)
            assert wrong['manifest']['status']=='unavailable'
            assert 'inventory_unavailable' in wrong['preflight']['blockers']
            absent=await preflight(factory,target,tmp_path/'absent',runtime=RUNTIME)
            assert 'storage_unavailable' in absent['preflight']['blockers']
            # Same server, restricted current role: activity/administrative
            # capability must not be assumed from a successful SQL connection.
            limited=create_async_engine(postgres,hide_parameters=True)
            @event.listens_for(limited.sync_engine,'connect')
            def set_role(conn,record):
                cursor=conn.cursor();cursor.execute(f'SET ROLE {role}');cursor.close()
            try:
                async with async_sessionmaker(limited)() as db:
                    observed=await database_observations(db)
                    assert not observed['full_activity_visibility']
                    decision=assess(observed,dict(status='observed'),RUNTIME,True)
                    assert 'maintenance_privileges_not_established' in decision['blockers']
            finally:
                await limited.dispose()
        finally:
            await engine.dispose()
    asyncio.run(scenario())
