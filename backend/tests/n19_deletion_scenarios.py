"""Actual deletion scenarios; invoked only in a fresh labelled isolated N19 lab."""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4,UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.services.candidate_inventory import Target,InventoryError
from app.services.submission_deletion import preview,delete_submission,DeletionError,exact_file,import_suppressed

ROOT=Path('/cv')
REF='TT-JOB-0123456789ABCDEF'

def engine():
    return create_async_engine(settings.database_url.get_secret_value(),poolclass=NullPool,hide_parameters=True)

async def seed():
    e=engine();f=async_sessionmaker(e)
    try:
        async with f.begin() as db:
            assert await db.scalar(text('SELECT current_database()'))=='n19_lab'
            assert await db.scalar(text('SELECT version_num FROM alembic_version'))=='0016_submission_deletion'
            assert await db.scalar(text('SELECT count(*) FROM recruiters'))==0
            owner,job=uuid4(),uuid4()
            await db.execute(text("INSERT INTO recruiters VALUES (:id,'n19-fictional@example.test','unused',true)"),{'id':owner})
            await db.execute(text("INSERT INTO job_profiles(id,recruiter_id,job_reference,job_title,revision,sources,suggestions,scoring_weights) VALUES (:job,:owner,:ref,'Synthetic deletion',1,'[]','{}',:weights)"),dict(job=job,owner=owner,ref=REF,weights=json.dumps(dict(skill=100,experience=0,education=0))))
            targets=[]
            for i in range(3):
                t=Target(owner,job,uuid4(),uuid4());targets.append({k:str(v) for k,v in t.parameters().items()})
                data=b'%PDF-1.4\nsynthetic-'+str(i).encode()+b'\n%%EOF'
                p=exact_file(ROOT,t,REF,'pdf');p.parent.mkdir(parents=True);p.write_bytes(data)
                await db.execute(text("INSERT INTO external_cv_submissions(id,job_id,source_job_reference,source_id,external_submission_id,batch_id,upload_id,file_type,size_bytes,content_sha256,status) VALUES (:id,:job_id,:ref,'synthetic_source',:sid,:batch_id,:upload_id,'pdf',:size,:digest,'pending_review')"),dict(t.parameters(),id=uuid4(),ref=REF,sid='submission-'+str(i),size=len(data),digest=hashlib.sha256(data).hexdigest()))
                for rev in (1,2):
                    await db.execute(text("INSERT INTO candidate_scores(id,job_id,batch_id,upload_id,criteria_revision,scoring_version,score,payload) VALUES (:id,:job_id,:batch_id,:upload_id,:rev,'synthetic',100,'{}')"),dict(t.parameters(),id=uuid4(),rev=rev))
                await db.execute(text('INSERT INTO application_views(job_id,batch_id,upload_id) VALUES (:job_id,:batch_id,:upload_id)'),t.parameters())
            # Related CV-only confirmation is deleted explicitly before F2 rows.
            t=Target(**{k:UUID(v) for k,v in targets[0].items()})
            await db.execute(text("INSERT INTO reviewer_confirmations(id,job_id,batch_id,upload_id,reviewer_id,version,criteria_revision,position,scope,requirement_ids,evidence_references,source_versions,source_digest,confirmed_at,expires_at) VALUES (:id,:job_id,:batch_id,:upload_id,:recruiter_id,1,1,'alignment','cv_only','[]','[]','{}',:digest,now(),now()+interval '1 day')"),dict(t.parameters(),id=uuid4(),digest='a'*64))
        (ROOT/'synthetic-targets.json').write_text(json.dumps(targets))
        print('synthetic_seed_verified')
    finally:await e.dispose()

async def scenarios():
    e=engine();f=async_sessionmaker(e)
    targets=[Target(**{k:UUID(v) for k,v in t.items()}) for t in json.loads((ROOT/'synthetic-targets.json').read_text())]
    t,interrupted,other=targets
    passed=[]
    async def refuse(fn,codes=None):
        try:await fn()
        except (DeletionError,InventoryError) as err:
            if codes:assert str(err) in codes,str(err)
        else:raise AssertionError('unsafe_action_not_refused')
    try:
        wrong=Target(uuid4(),t.job_id,t.batch_id,t.upload_id)
        await refuse(lambda:preview(f,wrong,ROOT));passed.append('wrong_owner_rejected')
        missing=Target(t.recruiter_id,t.job_id,t.batch_id,uuid4())
        await refuse(lambda:preview(f,missing,ROOT));passed.append('missing_target_rejected')
        plan=await preview(f,t,ROOT)
        # An interview scope is deliberately unsupported, even without F5 text.
        interview=uuid4()
        async with f.begin() as db:
            await db.execute(text("INSERT INTO interview_schedules(id,recruiter_id,job_id,batch_id,upload_id,criteria_revision,scoring_version,scheduled_at,timezone,duration_minutes,unscored_confirmed,screening_snapshot) VALUES (:id,:recruiter_id,:job_id,:batch_id,:upload_id,1,'synthetic',now()+interval '1 day','UTC',60,false,'{}')"),dict(t.parameters(),id=interview))
        await refuse(lambda:preview(f,t,ROOT));passed.append('interview_scope_rejected')
        async with f.begin() as db:await db.execute(text('DELETE FROM interview_schedules WHERE id=:id'),{'id':interview})
        # A reused batch/upload in another job must not be absorbed into this scope.
        foreign_job,foreign_owner,foreign_score=uuid4(),uuid4(),uuid4()
        async with f.begin() as db:
            await db.execute(text("INSERT INTO recruiters VALUES (:id,'other-n19-fictional@example.test','unused',true)"),{'id':foreign_owner})
            await db.execute(text("INSERT INTO job_profiles(id,recruiter_id,job_reference,job_title,revision,sources,suggestions,scoring_weights) VALUES (:job,:owner,'TT-JOB-FEDCBA9876543210','Other synthetic',1,'[]','{}',:weights)"),dict(job=foreign_job,owner=foreign_owner,weights=json.dumps(dict(skill=100,experience=0,education=0))))
            await db.execute(text("INSERT INTO candidate_scores(id,job_id,batch_id,upload_id,criteria_revision,scoring_version,score,payload) VALUES (:id,:foreign,:batch_id,:upload_id,1,'synthetic',100,'{}')"),dict(t.parameters(),id=foreign_score,foreign=foreign_job))
        await refuse(lambda:preview(f,t,ROOT));passed.append('cross_job_identity_reuse_rejected')
        async with f.begin() as db:await db.execute(text('DELETE FROM candidate_scores WHERE id=:id'),{'id':foreign_score})
        await refuse(lambda:delete_submission(f,t,ROOT,'0'*64),{'manifest_changed'});passed.append('changed_manifest_rejected')
        # Ambiguous alternate file is refused without changing the original.
        p=exact_file(ROOT,t,REF,'docx');p.write_bytes(b'synthetic ambiguous')
        await refuse(lambda:preview(f,t,ROOT));p.unlink();passed.append('ambiguous_file_rejected')
        # A shared job JSON row blocks cleanup rather than deleting another applicant.
        async with f.begin() as db:
            await db.execute(text("INSERT INTO bulk_scheduling_operations(id,recruiter_id,job_id,criteria_revision,fingerprint,status,created_at,updated_at,expires_at,preview,outcomes) VALUES (:id,:owner,:job,1,'synthetic','preview',now(),now(),now()+interval '1 day','{}','[]')"),dict(id=uuid4(),owner=t.recruiter_id,job=t.job_id))
        await refuse(lambda:preview(f,t,ROOT));passed.append('shared_json_rejected')
        async with f.begin() as db:await db.execute(text('DELETE FROM bulk_scheduling_operations'))
        # Actual independent open DB client prevents deletion, not merely process hints.
        async with e.connect() as connection:
            await connection.execute(text('SELECT 1'))
            await refuse(lambda:delete_submission(f,t,ROOT,plan['digest']),{'other_database_clients'})
        passed.append('concurrent_client_rejected')
        result=await delete_submission(f,t,ROOT,plan['digest']);assert result['state']=='complete'
        assert not exact_file(ROOT,t,REF,'pdf').exists()
        async with f() as db:
            for table in ['candidate_scores','application_views','external_cv_submissions','reviewer_confirmations']:
                assert await db.scalar(text(f'SELECT count(*) FROM {table} WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id'),t.parameters())==0
            assert await db.scalar(text('SELECT count(*) FROM candidate_scores'))==4
            assert await import_suppressed(db,'synthetic_source','submission-0')
        passed.append('selected_related_rows_and_file_deleted')
        # SQL insert replay rejected even if an importer bypasses Python helper.
        try:
            async with f.begin() as db:
                await db.execute(text("INSERT INTO external_cv_submissions(id,job_id,source_job_reference,source_id,external_submission_id,batch_id,upload_id,file_type,size_bytes,content_sha256,status) VALUES (:id,:job_id,:ref,'synthetic_source','submission-0',:batch_id,:upload_id,'pdf',1,:digest,'pending_review')"),dict(t.parameters(),id=uuid4(),ref=REF,digest='b'*64))
        except Exception as err:
            assert 'external_submission_deleted' in str(err)
        else:raise AssertionError('replay_not_blocked')
        passed.append('database_replay_fence')
        await delete_submission(f,t,ROOT,plan['digest']);passed.append('completed_retry_idempotent')
        second=await preview(f,interrupted,ROOT)
        def crash():raise RuntimeError('synthetic_interruption')
        try:await delete_submission(f,interrupted,ROOT,second['digest'],after_commit=crash)
        except RuntimeError as err:assert str(err)=='synthetic_interruption'
        else:raise AssertionError('interruption_missing')
        assert exact_file(ROOT,interrupted,REF,'pdf').is_file()
        async with f() as db:
            assert await db.scalar(text('SELECT state FROM submission_deletions WHERE upload_id=:upload_id'),interrupted.parameters())=='file_pending'
            assert await import_suppressed(db,'synthetic_source','submission-1')
        original=exact_file(ROOT,interrupted,REF,'pdf').read_bytes()
        exact_file(ROOT,interrupted,REF,'pdf').write_bytes(b'synthetic changed file')
        await refuse(lambda:delete_submission(f,interrupted,ROOT,second['digest']),{'file_integrity_changed'})
        exact_file(ROOT,interrupted,REF,'pdf').write_bytes(original)
        passed.append('changed_file_blocks_retry')
        await delete_submission(f,interrupted,ROOT,second['digest'])
        assert not exact_file(ROOT,interrupted,REF,'pdf').exists();passed.append('interrupted_commit_retry')
        assert exact_file(ROOT,other,REF,'pdf').is_file()
        async with f() as db:assert await db.scalar(text('SELECT count(*) FROM candidate_scores'))==2
        passed.append('unrelated_submission_preserved')
        # Public internal importer refuses BEFORE creating new storage, under owned job lock.
        from app.services.external_cv import ExternalCvImportService,ExternalCvImportError
        from app.schemas.external_cv import ApprovedExternalSource,ExternalCvSubmission
        from starlette.datastructures import UploadFile,Headers
        from io import BytesIO
        service=ExternalCvImportService(f,ROOT,(ApprovedExternalSource(source_id='synthetic_source',recruiter_id=t.recruiter_id,job_id=t.job_id),))
        payload=ExternalCvSubmission(source_id='synthetic_source',external_submission_id='submission-0',source_job_reference=REF,job_reference=REF,synthetic=True,cv=UploadFile(BytesIO(b'%PDF-1.4\nsynthetic\n%%EOF'),filename='synthetic.pdf',headers=Headers({'content-type':'application/pdf'})))
        try:await service.import_submission(payload)
        except ExternalCvImportError as err:assert err.code=='submission_deleted'
        else:raise AssertionError('importer_replayed_deleted_source')
        passed.append('importer_replay_suppressed')
        print(json.dumps({'passed':passed,'count':len(passed),'scope':'synthetic_exact_imports_only'}))
    finally:await e.dispose()
