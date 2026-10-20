"""Bounded imported-submission deletion, ONLY inside the N19 disposable lab.

Not person-wide deletion. No endpoint. Maintenance remains closed after success
or failure. PostgreSQL commit precedes exact file unlink; a minimal tombstone is
also the durable retry journal. External copies, WAL and backups are out of scope.
"""
import hashlib
import json
import os
import stat
from pathlib import Path
from sqlalchemy import text
from app.services.candidate_inventory import Target, QUERIES, inventory, inventory_in_transaction
from app.schemas.cv_upload import CvBatchInput


class DeletionError(Exception):
    """Fixed diagnostic codes; never include source records, paths or credentials."""


def source_digest(source, submission):
    return hashlib.sha256(source.encode() + b'\0' + submission.encode()).hexdigest()


async def import_suppressed(db, source, submission):
    # Existing installations at 0015 have never supported this deletion path.
    if not await db.scalar(text("SELECT to_regclass('public.submission_deletions')")):
        return False
    return bool(await db.scalar(text('SELECT 1 FROM submission_deletions WHERE source_digest=:digest'),
                                {'digest': source_digest(source, submission)}))


def exact_file(root, target, reference, kind):
    target.parameters()
    CvBatchInput(job_reference=reference)
    if kind not in {'pdf', 'docx'}:
        raise DeletionError('unsafe_file_type')
    root = Path(root).absolute()
    path = root / str(target.recruiter_id) / reference / str(target.batch_id) / (str(target.upload_id)+'.'+kind)
    if root == Path(root.anchor):
        raise DeletionError('unsafe_storage')
    for p in [path, *path.parents]:
        if p.is_symlink() or p.is_junction():
            raise DeletionError('unsafe_storage')
    if path.exists() and (not stat.S_ISREG(path.stat().st_mode) or path.stat().st_nlink != 1):
        raise DeletionError('unsafe_storage')
    return path


def fingerprint(path):
    # Source CV size is bounded by the existing importer. Never read unbounded data.
    if path.stat().st_size > 10*1024*1024:
        raise DeletionError('file_integrity_changed')
    with path.open('rb') as f:
        return hashlib.sha256(f.read(10*1024*1024+1)).hexdigest()


def validate_inventory(observed):
    allowed = {'imported_submissions', 'screening_versions', 'f6_confirmations', 'acknowledgements', 'cv_files'}
    outside = {'global_candidate_identity', 'external_copies_and_backups', 'f11_and_inflight_processing'}
    for name, category in observed['categories'].items():
        if name in outside:
            continue  # disclosed scope limits, not evidence of deletion completeness
        if category['status'] in {'ambiguous', 'unsupported'}:
            raise DeletionError('incomplete_or_ambiguous_inventory')
        if name not in allowed and category['count']:
            raise DeletionError('related_records_not_supported')
    if observed['categories']['imported_submissions']['count'] != 1:
        raise DeletionError('exact_import_required')
    if observed['categories']['cv_files']['count'] != 1:
        raise DeletionError('exact_file_required')


async def boundary(db, root):
    lab = os.environ.get('N19_LAB_ID', '')
    if not lab.startswith('tt-n19-lab-') or os.getuid() != 10002:
        raise DeletionError('isolated_maintenance_required')
    root = Path(root).absolute()
    if root != Path('/cv') or root.is_symlink() or root.stat().st_uid != 10002 or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise DeletionError('storage_boundary_unavailable')
    try:
        marker = json.loads((root/'.n19-maintenance.json').read_text())
    except (OSError, ValueError):
        raise DeletionError('maintenance_marker_unavailable') from None
    if marker != {'lab': lab, 'state': 'maintenance'}:
        raise DeletionError('maintenance_marker_mismatch')
    identity = (await db.execute(text('SELECT current_database(),current_user'))).one()
    if tuple(identity) != ('n19_lab', 'n19_maintenance'):
        raise DeletionError('wrong_database_or_role')
    if await db.scalar(text("SELECT rolcanlogin FROM pg_roles WHERE rolname='n19_application'")) is not False:
        raise DeletionError('writer_admission_open')
    if await db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'")):
        raise DeletionError('other_database_clients')
    if await db.scalar(text('SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()')):
        raise DeletionError('prepared_transactions')


async def preview(factory, target, root):
    target.parameters()
    async with factory() as db:
        async with db.begin():
            await boundary(db, root)
        observed = await inventory(db, target, root)
        validate_inventory(observed)
        async with db.begin():
            row = (await db.execute(text('SELECT e.file_type,e.content_sha256,e.source_id,e.external_submission_id,j.job_reference FROM external_cv_submissions e JOIN job_profiles j ON j.id=e.job_id WHERE e.job_id=:job_id AND e.batch_id=:batch_id AND e.upload_id=:upload_id AND j.recruiter_id=:recruiter_id'), target.parameters())).mappings().one_or_none()
            if row is None:
                raise DeletionError('owned_import_not_found')
            path = exact_file(root, target, row['job_reference'], row['file_type'])
            if fingerprint(path) != row['content_sha256']:
                raise DeletionError('file_integrity_changed')
    return make_plan(target, observed, row['content_sha256'],source_digest(row['source_id'],row['external_submission_id']))


def make_plan(target, observed, digest, source=None):
    data = dict(version=1, scope='one_imported_submission_not_person', target={k:str(v) for k,v in target.parameters().items()},
                counts={k:v['count'] for k,v in observed['categories'].items() if v['count']}, file_digest=digest,source_digest=source)
    return dict(digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(), plan=data)


async def delete_submission(factory, target, root, expected_digest, *, after_commit=None):
    """Retry by the SAME exact four IDs. No automatic restoration or admission reopen."""
    target.parameters()
    async with factory() as db:
        async with db.begin():
            await boundary(db, root)
            # Lock order follows ordinary writers: job first. Maintenance admission is
            # the real exclusion boundary, not the advisory nature of this row lock.
            job = await db.scalar(text('SELECT job_reference FROM job_profiles WHERE id=:job_id AND recruiter_id=:recruiter_id FOR UPDATE'),target.parameters())
            if job is None:
                raise DeletionError('owned_job_not_found')
            journal = (await db.execute(text('SELECT * FROM submission_deletions WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id FOR UPDATE'),target.parameters())).mappings().one_or_none()
            if journal and journal['recruiter_id'] != target.recruiter_id:
                raise DeletionError('journal_owner_mismatch')
        # A fresh preview owns a read-only transaction. This connection is closed
        # first: boundary correctly rejects other clients, even this CLI's own pool.
    # NullPool is required by the controller, so no idle client survives here.
    if journal is not None and journal['plan_digest'] != expected_digest:
        raise DeletionError('manifest_changed')
    if journal is None:
        plan = await preview(factory, target, root)
        if plan['digest'] != expected_digest:
            raise DeletionError('manifest_changed')
    async with factory() as db:
        async with db.begin():
            await boundary(db, root)
            # No mutation before rechecking owner and bounded inventory. Lock every
            # supported source table while taking the final read-only inventory in
            # this transaction; the pure count checks below match the preview rules.
            await db.execute(text('LOCK TABLE job_profiles, external_cv_submissions, candidate_scores, interview_schedules, scheduling_invitations, reviewer_confirmations, application_views, bulk_scheduling_operations IN EXCLUSIVE MODE NOWAIT'))
            job = await db.scalar(text('SELECT job_reference FROM job_profiles WHERE id=:job_id AND recruiter_id=:recruiter_id'),target.parameters())
            if job is None:
                raise DeletionError('owned_job_not_found')
            journal = (await db.execute(text('SELECT * FROM submission_deletions WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id FOR UPDATE'),target.parameters())).mappings().one_or_none()
            if journal is None:
                observed=await inventory_in_transaction(db,target,root)
                validate_inventory(observed)
                row = (await db.execute(text('SELECT * FROM external_cv_submissions WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id'),target.parameters())).mappings().one_or_none()
                if row is None:
                    raise DeletionError('owned_import_not_found')
                path = exact_file(root,target,job,row['file_type'])
                if not path.exists() or fingerprint(path)!=row['content_sha256']:
                    raise DeletionError('file_integrity_changed')
                if make_plan(target,observed,row['content_sha256'],source_digest(row['source_id'],row['external_submission_id']))['digest']!=expected_digest:
                    raise DeletionError('manifest_changed')
                values=dict(target.parameters(),plan_digest=expected_digest,source_digest=source_digest(row['source_id'],row['external_submission_id']),file_digest=row['content_sha256'],job_reference=job,file_type=row['file_type'])
                await db.execute(text("INSERT INTO submission_deletions(job_id,batch_id,upload_id,recruiter_id,plan_digest,source_digest,file_digest,job_reference,file_type,state) VALUES (:job_id,:batch_id,:upload_id,:recruiter_id,:plan_digest,:source_digest,:file_digest,:job_reference,:file_type,'file_pending')"),values)
                for table in ('reviewer_confirmations','application_views','candidate_scores','external_cv_submissions'):
                    await db.execute(text(f'DELETE FROM {table} WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id'),target.parameters())
                journal=values | {'state':'file_pending'}
            elif journal['plan_digest']!=expected_digest:
                raise DeletionError('manifest_changed')
            elif journal['recruiter_id']!=target.recruiter_id:
                raise DeletionError('journal_owner_mismatch')
    # SQL commit happened. A crash now leaves a durable replay fence/file_pending.
    if after_commit:
        after_commit()
    path=exact_file(root,target,journal['job_reference'],journal['file_type'])
    if path.exists():
        if fingerprint(path)!=journal['file_digest']:
            raise DeletionError('file_integrity_changed')
        path.unlink()
        fd=os.open(path.parent,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    async with factory() as db:
        async with db.begin():
            await boundary(db,root)
            for table,predicate in QUERIES.values():
                if await db.scalar(text(f'SELECT count(*) FROM {table} WHERE {predicate}'),target.parameters()):
                    raise DeletionError('residual_records')
            if path.exists():raise DeletionError('residual_file')
            await db.execute(text("UPDATE submission_deletions SET state='complete' WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id AND recruiter_id=:recruiter_id"),target.parameters())
    return dict(state='complete',scope='one_imported_submission_not_person',maintenance='remains_closed')


async def deletion_status(factory, target, root):
    target.parameters()
    async with factory() as db:
        async with db.begin():
            await boundary(db, root)
            owned = await db.scalar(text('SELECT 1 FROM job_profiles WHERE id=:job_id AND recruiter_id=:recruiter_id'),target.parameters())
            if not owned:raise DeletionError('owned_job_not_found')
            row = (await db.execute(text('SELECT recruiter_id,state FROM submission_deletions WHERE job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id'),target.parameters())).mappings().one_or_none()
            if row is not None and row['recruiter_id']!=target.recruiter_id:
                raise DeletionError('journal_owner_mismatch')
            return dict(state=row['state'] if row else 'not_started',scope='one_imported_submission_not_person',maintenance='remains_closed')
