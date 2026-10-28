"""Synthetic inventory tests. PostgreSQL test explicitly opts into disposable Docker."""
import asyncio
import json
import os
from io import StringIO
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services.candidate_inventory import Target, InventoryError, file_inventory, inventory


def test_current_booked_email_foreign_key_is_in_the_inventory():
    from app.db.models.recruiter import BookedInterviewEmailAttempt
    from app.services.candidate_inventory import QUERIES
    assert BookedInterviewEmailAttempt.__tablename__ in {table for table, _ in QUERIES.values()}


@pytest.fixture
def target():
    return Target(uuid4(), uuid4(), uuid4(), uuid4())


def batch(root, target):
    return root / str(target.recruiter_id) / 'TT-JOB-0123456789ABCDEF' / str(target.batch_id)


def test_exact_file_in_multi_application_batch(tmp_path, target):
    directory = batch(tmp_path, target)
    directory.mkdir(parents=True)
    (directory / f'{target.upload_id}.pdf').write_bytes(b'fictional')
    (directory / f'{uuid4()}.pdf').write_bytes(b'unrelated')
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert file_inventory(tmp_path, target, 'TT-JOB-0123456789ABCDEF') == {
        'status': 'confirmed', 'count': 1, 'reason': 'exact_supported_filename'}
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_missing_and_ambiguous_files(tmp_path, target):
    assert file_inventory(tmp_path, target, 'TT-JOB-0123456789ABCDEF')['status'] == 'missing'
    directory = batch(tmp_path, target)
    directory.mkdir(parents=True)
    for suffix in ('.pdf', '.docx'):
        (directory / f'{target.upload_id}{suffix}').touch()
    assert file_inventory(tmp_path, target, 'TT-JOB-0123456789ABCDEF')['status'] == 'ambiguous'


@pytest.mark.parametrize('link_parent', [True, False])
def test_links_are_not_followed(tmp_path, target, link_parent, monkeypatch):
    directory = batch(tmp_path, target)
    directory.parent.mkdir(parents=True)
    outside = tmp_path / 'unrelated'
    outside.mkdir()
    try:
        if link_parent:
            directory.symlink_to(outside, target_is_directory=True)
        else:
            directory.mkdir()
            (outside / 'private').write_bytes(b'never read')
            (directory / f'{target.upload_id}.pdf').symlink_to(outside / 'private')
    except OSError:
        # Windows may deny link creation without developer privileges. Exercise
        # the same guard deterministically; do not require elevated tests.
        unsafe = directory if link_parent else directory / f'{target.upload_id}.pdf'
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda p: p == unsafe or original(p))
    assert file_inventory(tmp_path, target, 'TT-JOB-0123456789ABCDEF')['reason'] == 'unsafe_storage_path'


def test_unsafe_reference_and_identity(tmp_path, target):
    assert file_inventory(tmp_path, target, '../../outside')['status'] == 'unsupported'
    with pytest.raises(InventoryError):
        Target('not-a-uuid', uuid4(), uuid4(), uuid4()).parameters()


def test_fresh_transaction_required(tmp_path, target):
    class ExistingTransaction:
        def in_transaction(self):
            return True
    with pytest.raises(InventoryError, match='fresh_session_required'):
        asyncio.run(inventory(ExistingTransaction(), target, tmp_path))


def test_cli_invalid_identity_does_not_echo_input():
    result = subprocess.run([sys.executable, '-m', 'app.candidate_inventory',
        '--recruiter-id', 'sensitive@example.test'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'sensitive@example.test' not in result.stderr


@pytest.fixture(scope='module')
def postgres():
    if os.environ.get('N19_TEST_PG') != '1':
        pytest.skip('Set N19_TEST_PG=1 for disposable PostgreSQL test')
    from alembic import command
    from alembic.config import Config
    name = 'tt-n19-test-' + uuid4().hex[:10]
    password = uuid4().hex
    def docker(*args, input=None):
        result = subprocess.run(['docker', *args], input=input, capture_output=True, text=True)
        assert result.returncode == 0, 'Disposable PostgreSQL operation failed (details withheld)'
        return result.stdout.strip()
    # Existing image only; never pull or use an existing application volume.
    image = os.environ.get('N19_TEST_IMAGE', 'pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f')
    docker('image', 'inspect', image)
    docker('run', '--pull=never', '-d', '--name', name, '--label', 'talenttrace.test=n19',
           '-e', 'POSTGRES_USER=n19', '-e', 'POSTGRES_DB=n19_test', '-e', 'POSTGRES_PASSWORD='+password,
           '-p', '127.0.0.1::5432', image)
    try:
        for _ in range(60):
            result = subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'n19', '-d', 'n19_test'], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(.25)
        else:
            pytest.fail('Disposable PostgreSQL readiness failed')
        sql = StringIO()
        command.upgrade(Config('alembic.ini', output_buffer=sql), 'head', sql=True)
        docker('exec', '-i', name, 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'n19', '-d', 'n19_test', input=sql.getvalue())
        port = docker('port', name, '5432/tcp').rsplit(':', 1)[1]
        yield f'postgresql+asyncpg://n19:{password}@127.0.0.1:{port}/n19_test'
    finally:
        # Only this uniquely named test container, never any project container.
        docker('rm', '-f', name)


def test_postgres_inventory_read_only_scope_and_dependencies(postgres, tmp_path, target):
    async def scenario():
        engine = create_async_engine(postgres, hide_parameters=True)
        factory = async_sessionmaker(engine)
        p = target.parameters()
        other_job, other_upload, interview, capture, scheduling = [uuid4() for _ in range(5)]
        async def insert(db, table, values):
            keys = list(values)
            await db.execute(text(f'INSERT INTO {table} ({",".join(keys)}) VALUES ({",".join(":"+k for k in keys)})'), values)
        try:
            async with factory.begin() as db:
                await insert(db, 'recruiters', dict(id=target.recruiter_id,email='fictional@example.test',password_hash='unused',active=True))
                for job, ref in [(target.job_id, 'TT-JOB-0123456789ABCDEF'), (other_job, 'TT-JOB-FEDCBA9876543210')]:
                    await insert(db, 'job_profiles', dict(id=job,recruiter_id=target.recruiter_id,job_reference=ref,job_title='Synthetic',revision=2,confirmed_snapshot='{}',sources='[]',suggestions='{}',scoring_weights='{"skill":100,"experience":0,"education":0}'))
                for job, upload, revision in [(target.job_id,target.upload_id,1),(target.job_id,target.upload_id,2),(target.job_id,other_upload,2),(other_job,target.upload_id,2)]:
                    await insert(db,'candidate_scores',dict(id=uuid4(),job_id=job,batch_id=target.batch_id,upload_id=upload,criteria_revision=revision,scoring_version='synthetic',score=100,payload='{"private":"must-not-leak"}'))
                now=datetime.now(timezone.utc)
                await insert(db,'interview_schedules',dict(id=interview,recruiter_id=target.recruiter_id,job_id=target.job_id,batch_id=target.batch_id,upload_id=target.upload_id,criteria_revision=2,scoring_version='synthetic',scheduled_at=now,timezone='UTC',duration_minutes=60,unscored_confirmed=False,screening_snapshot='{"private":"must-not-leak"}'))
                await insert(db,'interview_invitations',dict(id=uuid4(),interview_id=interview,token_hash='s'*64,expires_at=now+timedelta(hours=1),revoked=False))
                await insert(db,'booked_interview_email_attempts',dict(interview_id=interview,status='uncertain',created_at=now))
                other_interview=uuid4()
                await insert(db,'interview_schedules',dict(id=other_interview,recruiter_id=target.recruiter_id,job_id=target.job_id,batch_id=target.batch_id,upload_id=other_upload,criteria_revision=2,scoring_version='synthetic',scheduled_at=now,timezone='UTC',duration_minutes=60,unscored_confirmed=False,screening_snapshot='{}'))
                await insert(db,'booked_interview_email_attempts',dict(interview_id=other_interview,status='accepted',created_at=now))
                await insert(db,'interview_transcript_sessions',dict(id=capture,interview_id=interview,started_at=now,recruiter_consented_at=now,candidate_consented_at=now,consent_version='synthetic',status='active',persistence_outcome='pending'))
                await insert(db,'interview_transcript_turns',dict(id=uuid4(),session_id=capture,sequence=1,role='candidate',text='private fictional text',start_ms=0,end_ms=10,created_at=now))
                await insert(db,'application_views',dict(job_id=target.job_id,batch_id=target.batch_id,upload_id=target.upload_id))
                await insert(db,'external_cv_submissions',dict(id=uuid4(),job_id=target.job_id,source_job_reference='TT-JOB-0123456789ABCDEF',source_id='synthetic',external_submission_id='fictional-source-id',batch_id=target.batch_id,upload_id=target.upload_id,file_type='pdf',size_bytes=8,content_sha256='a'*64,status='pending_review'))
                await insert(db,'scheduling_invitations',dict(id=scheduling,recruiter_id=target.recruiter_id,job_id=target.job_id,batch_id=target.batch_id,upload_id=target.upload_id,criteria_revision=2,token_hash='a'*64,expires_at=now+timedelta(hours=1),unscored_confirmed=False,revoked=False,interview_id=interview))
                await insert(db,'interview_email_attempts',dict(id=uuid4(),scheduling_invitation_id=scheduling,kind='scheduling',status='failed',created_at=now))
                await insert(db,'interview_analyses',dict(id=uuid4(),interview_id=interview,recruiter_id=target.recruiter_id,job_id=target.job_id,input_digest='b'*64,criteria_revision=2,rubric_version='synthetic',provider='none',model='none',corpus_version='synthetic',status='failed',attempt=1,claim=uuid4(),lease_expires_at=now,created_at=now,updated_at=now))
                await insert(db,'reviewer_confirmations',dict(id=uuid4(),job_id=target.job_id,batch_id=target.batch_id,upload_id=target.upload_id,reviewer_id=target.recruiter_id,interview_id=interview,version=1,position='insufficient',scope='cv_interview',criteria_revision=2,requirement_ids='[]',evidence_references='[]',source_versions='{}',source_digest='c'*64,confirmed_at=now,expires_at=now+timedelta(days=1)))
                await insert(db,'bulk_scheduling_operations',dict(id=uuid4(),recruiter_id=target.recruiter_id,job_id=target.job_id,criteria_revision=2,fingerprint='d'*64,status='preview',created_at=now,updated_at=now,expires_at=now+timedelta(minutes=10),preview='{"candidates":[]}',outcomes='[]'))
            async def digest(db):
                tables=(await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
                return {table:await db.scalar(text(f"SELECT md5(string_agg(row_to_json(t)::text,'' ORDER BY row_to_json(t)::text)) FROM {table} t")) for table in tables}
            async with factory() as db:
                before=await digest(db)
            statements=[]
            def observed(conn,cursor,statement,parameters,context,executemany):
                statements.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',observed)
            try:
                async with factory() as db:
                    result=await inventory(db,target,tmp_path)
            finally:
                event.remove(engine.sync_engine,'before_cursor_execute',observed)
            assert statements[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
            assert all(s.lstrip().upper().startswith(('SELECT','SET TRANSACTION')) for s in statements)
            c=result['categories']
            assert c['screening_versions']['count']==2
            assert c['interviews_and_screening_snapshots']['count']==1
            assert c['joining_invitations']['count']==1
            assert c['booked_email_attempts']['count']==1
            assert c['unmapped_referencing_tables']['count']==0
            assert c['transcript_sessions']['count']==1 and c['transcript_turns']['count']==1
            assert c['acknowledgements']['count']==1
            for name in ('imported_submissions','scheduling_invitations','email_attempts','f5_analyses','f6_confirmations'):
                assert c[name]['count']==1
            assert c['shared_bulk_operations']['status']=='ambiguous'
            assert c['legacy_cross_job_references']['status']=='ambiguous'
            assert c['cv_files']['status']=='missing'
            assert 'must-not-leak' not in json.dumps(result) and 'private fictional text' not in json.dumps(result)
            async with factory() as db:
                assert await digest(db)==before
            environment={**os.environ,'DATABASE_URL':postgres,'CV_UPLOAD_ROOT':str(tmp_path)}
            command_line=[sys.executable,'-m','app.candidate_inventory']
            for key,value in target.parameters().items():
                command_line.extend(['--'+key.replace('_','-'),str(value)])
            cli=await asyncio.to_thread(subprocess.run,command_line,env=environment,capture_output=True,text=True)
            assert cli.returncode==0,'Dry-run CLI failed; details withheld'
            assert json.loads(cli.stdout)['categories']['screening_versions']['count']==2
            async with factory() as db:
                assert await digest(db)==before
            async with factory.begin() as db:
                await db.execute(text('CREATE TABLE future_dependency (job_id uuid REFERENCES job_profiles(id))'))
            async with factory() as db:
                unknown=await inventory(db,target,tmp_path)
                assert unknown['categories']['unmapped_referencing_tables']['status']=='unsupported'
                assert unknown['categories']['unmapped_referencing_tables']['count']==1
            for wrong in [Target(uuid4(),target.job_id,target.batch_id,target.upload_id), Target(target.recruiter_id,uuid4(),target.batch_id,target.upload_id)]:
                async with factory() as db:
                    with pytest.raises(InventoryError,match='owned_job_not_found'):
                        await inventory(db,wrong,tmp_path)
            async with factory() as db:
                async with db.begin():
                    await db.execute(text('SET TRANSACTION READ ONLY'))
                    with pytest.raises(Exception):
                        await db.execute(text("UPDATE job_profiles SET job_title='forbidden'"))
        finally:
            await engine.dispose()
    asyncio.run(scenario())
