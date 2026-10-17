"""Bounded, owned persisted identity union. No files, contact fields or F5 text."""
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.recruiter import CandidateScoreRecord, InterviewSchedule
from app.db.models.external_cv import ExternalCvSubmissionRecord
from app.schemas.consolidated_assessment import ApplicationDiscovery, DiscoveredApplication
from app.services.recruiter_records import owned_job
from app.services.consolidated_assessment import persisted_cv
from app.services.score_records import SCORING_VERSION

MAX_APPLICATIONS = 200
MAX_SCORE_ROWS = 500


async def discover_applications(db, owner, job_id):
    job = await owned_job(db, owner.id, job_id)  # Snapshot read; no additional locks.
    scores = (await db.scalars(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id == job.id)
        .order_by(CandidateScoreRecord.batch_id, CandidateScoreRecord.upload_id, CandidateScoreRecord.criteria_revision)
        .limit(MAX_SCORE_ROWS + 1))).all()
    interviews = (await db.scalars(select(InterviewSchedule).where(InterviewSchedule.job_id == job.id,
        InterviewSchedule.recruiter_id == owner.id).order_by(InterviewSchedule.id).limit(MAX_APPLICATIONS + 1))).all()
    # Project identities only; never load intake emails, contact status or content.
    ledger = (await db.execute(select(ExternalCvSubmissionRecord.batch_id, ExternalCvSubmissionRecord.upload_id)
        .where(ExternalCvSubmissionRecord.job_id == job.id).limit(MAX_APPLICATIONS + 1))).all()
    groups = defaultdict(list)
    for row in scores:
        groups[(row.batch_id, row.upload_id)].append(row)
    snapshots = {(r.batch_id, r.upload_id): r for r in interviews}
    identities = set(groups) | set(snapshots) | {(r.batch_id, r.upload_id) for r in ledger}
    if len(scores) > MAX_SCORE_ROWS or len(interviews) > MAX_APPLICATIONS or len(ledger) > MAX_APPLICATIONS or len(identities) > MAX_APPLICATIONS:
        raise HTTPException(409, 'Application discovery limit exceeded; no partial listing returned.')
    result = []
    for batch, upload in sorted(identities, key=lambda key: (key[0].hex, key[1].hex)):
        rows, interview = groups.get((batch, upload), []), snapshots.get((batch, upload))
        revisions = tuple(sorted({r.criteria_revision for r in rows} | ({interview.criteria_revision} if interview else set())))
        current = next((r for r in rows if r.criteria_revision == job.revision and r.scoring_version == SCORING_VERSION), None)
        kind, label = 'unavailable', 'Evidence unavailable or restricted'
        detail = ('Only historical F2 records survive; no current report is substituted.' if rows else
                  'Persisted application identity exists; no valid F2 evidence is available.')
        available, comparable, revision = False, False, None
        if interview or current:
            try:
                cv = persisted_cv(job, upload, row=current, interview=interview)
                revision = interview.criteria_revision if interview else current.criteria_revision
                available = True
                comparable = job.confirmed_snapshot is not None and revision == job.revision and cv.weights.model_dump() == job.scoring_weights
                if interview:
                    kind, label = 'historical_snapshot', 'Historical selection snapshot'
                    detail = 'Preserved CV evidence at interview selection. Interview consent/retention are checked separately on every report.'
                elif cv.status == 'scored':
                    kind, label = 'scored', 'Scored'
                    detail = 'Validated current saved F2 score and component evidence.'
                elif cv.screening_decision is not None:
                    kind, label = 'unscored', 'Screening evidence available; not scored'
                    detail = 'Persisted screening decision/reason only; requirement-level matches were not retained for unscored F2 payloads.'
                else:
                    detail = 'Persisted processing state exists; no reliable screening assessment is available.'
            except HTTPException as error:
                if error.status_code != 409:
                    raise
                detail = 'Persisted CV evidence could not be validated; no fallback or reconstruction was attempted.'
        result.append(DiscoveredApplication(job_id=job.id, batch_id=batch, upload_id=upload, kind=kind,
            label=label, detail=detail, evidence_revision=revision, recorded_revisions=revisions,
            report_available=available, comparison_available=comparable))
    return ApplicationDiscovery(job_id=job.id, criteria_revision=job.revision, applications=tuple(result))
