"""Read-only trusted batch discovery; no contacts, CV text or paths in replies."""
import hashlib
import hmac
import re
from collections import defaultdict
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.db.models.external_cv import ExternalCvSubmissionRecord as Import
from app.db.models.recruiter import CandidateScoreRecord
from app.services.cv_extraction import CvExtractionService
from app.services.cv_upload import validate_document
from app.services.bulk_scheduling import digest
from app.services.score_records import load_scores

MAX_RECORDS = 100


async def records(session, job, batch_id=None):
    query = select(Import.id, Import.job_id, Import.batch_id, Import.upload_id,
        Import.file_type, Import.size_bytes, Import.content_sha256, Import.status)
    query = query.where(Import.batch_id == batch_id) if batch_id else query.where(Import.job_id == job.id)
    rows = (await session.execute(query.order_by(Import.batch_id, Import.upload_id).limit(MAX_RECORDS + 1))).all()
    if len(rows) > MAX_RECORDS:
        raise HTTPException(409, 'Imported batch discovery exceeds the bounded review limit.')
    return rows


def verify_files(root, job, rows):
    if not rows or any(r.job_id != job.id or r.status != 'pending_review' for r in rows):
        raise ValueError('Unavailable association')
    files = CvExtractionService(root).batch_files(job.job_reference, rows[0].batch_id)
    expected = {f'{r.upload_id}.{r.file_type}': r for r in rows}
    if len(expected) != len(rows) or {p.name for p in files} != set(expected):
        raise ValueError('Unavailable identities')
    for path in files:
        row = expected[path.name]
        if path.stat().st_size != row.size_bytes:
            raise ValueError('Changed size')
        validate_document(path, row.file_type)
        sha = hashlib.sha256()
        with path.open('rb') as source:
            while block := source.read(1024 * 1024):
                sha.update(block)
        if sha.hexdigest() != row.content_sha256:
            raise ValueError('Changed file')


async def describe(session, job, rows, root):
    scores = (await session.scalars(select(CandidateScoreRecord).where(
        CandidateScoreRecord.job_id == job.id, CandidateScoreRecord.batch_id == rows[0].batch_id)
        .order_by(CandidateScoreRecord.id).limit(MAX_RECORDS + 1))).all()
    if len(scores) > MAX_RECORDS:
        raise HTTPException(409, 'Saved result history requires review.')
    state = 'older_revision' if scores else 'not_screened'
    if any(r.criteria_revision == job.revision for r in scores):
        try:
            saved = await load_scores(session, job, rows[0].batch_id)
            if {c.upload_id for c in saved.candidates} != {r.upload_id for r in rows}:
                raise ValueError()
            state = 'incomplete_results' if any(c.screening_decision is None for c in saved.candidates) else 'current_results'
        except (HTTPException, ValueError):
            state = 'incomplete_results'
    available = True
    try:
        await run_in_threadpool(verify_files, root, job, rows)
    except Exception:
        available = False
    # This is a freshness fingerprint, not authorization. The route must hold the
    # owned job row lock. Saved row identities change after a committed rerun.
    fingerprint = digest({'job': job.id, 'reference': job.job_reference, 'revision': job.revision,
        'criteria': job.confirmed_snapshot, 'weights': job.scoring_weights,
        'imports': [tuple(r) for r in rows],
        'scores': [(r.id, r.criteria_revision, r.scoring_version, r.payload) for r in scores]})
    return {'batch_id': rows[0].batch_id, 'upload_ids': [r.upload_id for r in rows],
        'availability': 'available' if available else 'unavailable', 'screening_status': state,
        'review_token': fingerprint if available else None}


async def discover(session, job, root):
    groups = defaultdict(list)
    for row in await records(session, job):
        groups[row.batch_id].append(row)
    batches = [await describe(session, job, rows, root) for rows in groups.values()]
    return {'job_id': job.id, 'job_reference': job.job_reference, 'criteria_revision': job.revision, 'batches': batches}


async def check_review(session, job, batch_id, root, token):
    rows = await records(session, job, batch_id)
    if not rows:
        if token is not None:
            raise HTTPException(409, 'Imported batch no longer available. Refresh its review.')
        return False  # Existing native upload flow.
    value = await describe(session, job, rows, root)
    if not token or not re.fullmatch(r"[a-f0-9]{64}", token) or not value['review_token'] or not hmac.compare_digest(token, value['review_token']):
        raise HTTPException(409, 'Imported batch, saved results or criteria changed. Refresh and review before screening.')
    return True
