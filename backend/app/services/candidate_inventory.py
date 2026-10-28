"""Privileged, count-only submission inventory. No deletion or lifecycle writes."""
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import text


class InventoryError(Exception):
    """Fixed public codes only; never include SQL, paths or personal data."""


@dataclass(frozen=True)
class Target:
    recruiter_id: UUID
    job_id: UUID
    batch_id: UUID
    upload_id: UUID

    def parameters(self):
        if not all(isinstance(v, UUID) for v in self.__dict__.values()):
            raise InventoryError('invalid_target')
        return dict(self.__dict__)


def file_inventory(root: Path, target: Target, reference: str):
    """Inspect exact upload names only; never follow a link or read CV contents."""
    from app.schemas.cv_upload import CvBatchInput
    try:
        CvBatchInput(job_reference=reference)
        target.parameters()
        root = root.absolute()
        if root == Path(root.anchor):
            return dict(status='unsupported', count=None, reason='unsafe_storage_root')
        batch = root / str(target.recruiter_id) / reference / str(target.batch_id)
        paths = [batch / (str(target.upload_id) + suffix) for suffix in ('.pdf', '.docx')]
        for path in [*batch.parents, batch, *paths]:
            if path.is_symlink() or path.is_junction():
                return dict(status='ambiguous', count=None, reason='unsafe_storage_path')
        if batch.exists() and not batch.is_dir():
            return dict(status='ambiguous', count=None, reason='unsafe_storage_path')
        found = [p for p in paths if p.exists()]
        if any(not p.is_file() for p in found):
            return dict(status='ambiguous', count=None, reason='unsafe_storage_path')
        if len(found) > 1:
            return dict(status='ambiguous', count=2, reason='multiple_upload_files')
        return dict(status='confirmed' if found else 'missing', count=len(found),
                    reason='exact_supported_filename' if found else 'cv_file_missing')
    except (OSError, ValueError):
        return dict(status='unsupported', count=None, reason='storage_inspection_failed')


# No JSON/text payload is returned to the operator. IDs below are explicit
# relational associations; batch/upload UUIDs alone are not foreign keys.
PAIR = 'job_id=:job_id AND batch_id=:batch_id AND upload_id=:upload_id'
INTERVIEWS = 'SELECT id FROM interview_schedules WHERE ' + PAIR
INVITES = 'SELECT id FROM scheduling_invitations WHERE ' + PAIR
QUERIES = {
    'imported_submissions': ('external_cv_submissions', PAIR),
    'screening_versions': ('candidate_scores', PAIR),
    'interviews_and_screening_snapshots': ('interview_schedules', PAIR),
    'scheduling_invitations': ('scheduling_invitations', PAIR),
    'joining_invitations': ('interview_invitations', f'interview_id IN ({INTERVIEWS})'),
    'email_attempts': ('interview_email_attempts', f'scheduling_invitation_id IN ({INVITES})'),
    'booked_email_attempts': ('booked_interview_email_attempts', f'interview_id IN ({INTERVIEWS})'),
    'transcript_sessions': ('interview_transcript_sessions', f'interview_id IN ({INTERVIEWS})'),
    'transcript_turns': ('interview_transcript_turns',
        f'session_id IN (SELECT id FROM interview_transcript_sessions WHERE interview_id IN ({INTERVIEWS}))'),
    'transcript_privacy_access': ('transcript_privacy_access', f'interview_id IN ({INTERVIEWS})'),
    'f5_analyses': ('interview_analyses', f'interview_id IN ({INTERVIEWS})'),
    'f6_confirmations': ('reviewer_confirmations',
        f'({PAIR}) OR interview_id IN ({INTERVIEWS})'),
    'acknowledgements': ('application_views', PAIR),
}


async def inventory(session, target: Target, storage_root: Path):
    """Own the transaction; REPEATABLE READ READ ONLY prevents accidental writes.

    Filesystem observations are not an atomic snapshot of the database. This is
    deliberately an inventory, never a deletion authorization or completeness proof.
    """
    if session.in_transaction():
        raise InventoryError('fresh_session_required')
    target.parameters()
    async with session.begin():
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        return await inventory_in_transaction(session, target, storage_root)


async def inventory_in_transaction(session, target: Target, storage_root: Path):
    """Shared association inventory; caller owns the transaction and isolation."""
    params = target.parameters()
    job = (await session.execute(text(
        'SELECT job_reference FROM job_profiles WHERE id=:job_id AND recruiter_id=:recruiter_id'), params)).scalar_one_or_none()
    if job is None:
        raise InventoryError('owned_job_not_found')
    tables = set((await session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars())
    categories = {}
    for name, (table, predicate) in QUERIES.items():
        # Include current dependencies through 0017. Missing dependencies fail closed
        # rather than silently running a partial join against older schemas.
        needed = {table}
        if 'interview_schedules' in predicate:
            needed.add('interview_schedules')
        if 'scheduling_invitations' in predicate:
            needed.add('scheduling_invitations')
        if 'interview_transcript_sessions' in predicate:
            needed.add('interview_transcript_sessions')
        if not needed <= tables:
            categories[name] = dict(status='unsupported', count=None, reason='schema_dependency_missing')
            continue
        count = await session.scalar(text(f'SELECT count(*) FROM {table} WHERE {predicate}'), params)
        categories[name] = dict(status='confirmed' if count else 'missing', count=count,
                                reason='exact_association' if count else 'no_associated_rows')
    # Shared job operations contain several submissions. Never claim the
    # whole row belongs to this upload, or return masked contacts/payloads.
    if 'bulk_scheduling_operations' in tables:
        count = await session.scalar(text(
            'SELECT count(*) FROM bulk_scheduling_operations WHERE job_id=:job_id'), params)
        categories['shared_bulk_operations'] = dict(status='ambiguous' if count else 'missing',
            count=count, reason='job_scoped_json_requires_review' if count else 'no_associated_rows')
    else:
        categories['shared_bulk_operations'] = dict(status='unsupported', count=None, reason='schema_dependency_missing')
    # No common application FK: a mismatched job on the same pair needs
    # review, not automatic inclusion in the deletion scope.
    legacy = 0
    for table in ('candidate_scores', 'external_cv_submissions', 'interview_schedules', 'scheduling_invitations'):
        if table in tables:
            legacy += await session.scalar(text(f'SELECT count(*) FROM {table} WHERE '
                'batch_id=:batch_id AND upload_id=:upload_id AND job_id<>:job_id'), params)
    categories['legacy_cross_job_references'] = dict(status='ambiguous' if legacy else 'missing',
        count=legacy, reason='pair_reused_outside_owned_job' if legacy else 'no_associated_rows')
    referencing = set((await session.execute(text("""
        SELECT DISTINCT child.relname FROM pg_constraint fk
        JOIN pg_class child ON child.oid=fk.conrelid
        JOIN pg_class parent ON parent.oid=fk.confrelid
        JOIN pg_namespace ns ON ns.oid=child.relnamespace
        WHERE fk.contype='f' AND ns.nspname='public'
          AND parent.relname IN ('job_profiles','candidate_scores','external_cv_submissions',
            'interview_schedules','interview_transcript_sessions','scheduling_invitations')
    """))).scalars())
    unknown = referencing - {value[0] for value in QUERIES.values()} - {'bulk_scheduling_operations'}
    categories['unmapped_referencing_tables'] = dict(status='unsupported' if unknown else 'missing',
        count=len(unknown), reason='unmapped_foreign_key_dependencies' if unknown else 'no_associated_rows')
    categories['cv_files'] = file_inventory(storage_root, target, job)
    categories['global_candidate_identity'] = dict(status='unsupported', count=None, reason='no_global_candidate_registry')
    categories['external_copies_and_backups'] = dict(status='unsupported', count=None, reason='outside_local_inventory')
    categories['f11_and_inflight_processing'] = dict(status='unsupported', count=None, reason='process_local_or_inflight_not_enumerable')
    blockers = sorted({v['reason'] for v in categories.values() if v['status'] in {'ambiguous', 'unsupported'}})
    if categories['cv_files']['status'] == 'missing':
        blockers.append('cv_file_missing')
    if not any(categories[k]['count'] for k in ('imported_submissions', 'screening_versions', 'interviews_and_screening_snapshots')) and not categories['cv_files']['count']:
        blockers.append('submission_not_established')
    return dict(mode='dry_run_only', mutation_performed=False, scope='single_owned_submission',
        categories=categories, blockers=blockers,
        limitations=['no_global_candidate_resolution', 'json_copies_not_exhaustively_resolved',
                     'filesystem_not_transactional', 'not_deletion_authorization'])
