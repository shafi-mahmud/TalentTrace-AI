"""Human confirmation of a fresh F6 projection. Never inference or source copying."""
import hashlib
import json
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, delete, text, or_
from app.db.models.reviewer_confirmation import ReviewerConfirmation as Record
from app.db.models.interview_analysis import InterviewAnalysis
from app.schemas.reviewer_confirmation import ConfirmationInput, ConfirmationView
from app.services.interview_transcripts import utc_now


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def evidence_token(report):
    return digest(report.model_dump(mode='json',exclude={'confirmation'}))


async def sources(db, report, scope):
    versions = {'criteria_revision': report.criteria_revision,
        'criteria_digest': digest([c.model_dump(mode='json') for c in report.confirmed_requirements]),
        'cv_source': report.cv_source, 'scoring_version': 'f2-coverage-v1',
        'cv_digest': digest(report.cv.model_dump(mode='json'))}
    if scope == 'cv_interview':
        i = report.interview
        if i.state != 'available':
            raise HTTPException(409, 'Interview evidence is not eligible for confirmation.')
        row = await db.get(InterviewAnalysis, i.operation_id)
        if row is None or row.status != 'completed':
            raise HTTPException(409, 'Interview evidence changed.')
        versions['f5'] = {'operation_id': str(row.id), 'input_digest': row.input_digest,
            'rubric_version': row.rubric_version, 'model': row.model, 'provider': row.provider,
            'corpus_version': row.corpus_version, 'result_digest': digest(row.result)}
    return versions


def validate_claims(report, body):
    criteria = {c.criterion_id:c for c in report.confirmed_requirements}
    scope = set(body.requirement_ids)
    if not criteria or not scope.issubset(criteria) or not {c.criterion_id for c in criteria.values() if c.is_hard}.issubset(scope):
        raise HTTPException(422, 'Use current confirmed requirements and include every mandatory requirement.')
    cv = {m.criterion_id:m for d in report.cv.dimensions for m in d.matches}
    interview = report.interview if body.scope == 'cv_interview' and report.interview.state == 'available' else None
    if body.scope == 'cv_interview' and interview is None:
        raise HTTPException(409, 'Interview evidence is not eligible for confirmation.')
    positive, concerns, gaps = set(), set(), set()
    for ref in body.references:
        if ref.criterion_id not in scope:
            raise HTTPException(422, 'Evidence must belong to the reviewed scope.')
        m = cv.get(ref.criterion_id)
        if ref.kind == 'cv':
            valid = m is not None and ((ref.reason == 'supported_requirement' and m.match_status == 'supported')
                or (ref.reason == 'uncertain_finding' and m.match_status == 'ambiguous')
                or (ref.reason == 'missing_evidence' and m.match_status == 'not_found'))
        elif ref.kind == 'interview' and interview is not None:
            mapping = next((r for r in interview.requirements if r.criterion_id == ref.criterion_id),None)
            answer = next((a for a in interview.assessment.answers if a.qa_id == ref.qa_id),None)
            dimension = next((d for d in answer.dimensions if d.dimension == ref.dimension),None) if answer else None
            valid = mapping is not None and ref.qa_id in mapping.qa_ids and dimension is not None and (
                (ref.reason == 'supported_requirement' and dimension.status == 'supported'
                 and ref.dimension in {'technical_accuracy','completeness'} and mapping.coverage == 'partial')
                or (ref.reason == 'documented_concern' and dimension.status == 'concern')
                or (ref.reason == 'uncertain_finding' and dimension.status in {'partial','uncertain'})
                or (ref.reason == 'missing_evidence' and dimension.status == 'not_assessed'))
        elif ref.kind == 'gap':
            mapping = next((r for r in interview.requirements if r.criterion_id == ref.criterion_id),None) if interview else None
            valid = ref.reason == 'missing_evidence' and (m is None or m.match_status != 'supported' or interview is None or mapping is None or mapping.coverage == 'not_evidenced')
        else:
            valid = False
        if not valid:
            raise HTTPException(422, 'Evidence reference or rationale is not supported by this report.')
        if ref.reason == 'supported_requirement':positive.add(ref.criterion_id)
        elif ref.reason in {'documented_concern','uncertain_finding'}:concerns.add(ref.criterion_id)
        else:gaps.add(ref.criterion_id)
    if body.position == 'alignment':
        # Missing/uncertain mandatory evidence cannot disappear behind a narrow scope.
        blockers = {id for id in scope if id in cv and cv[id].match_status == 'ambiguous'}
        if interview:
            for mapping in interview.requirements:
                if mapping.criterion_id not in scope:continue
                for answer in interview.assessment.answers:
                    if answer.qa_id in mapping.qa_ids and any(d.status == 'concern' for d in answer.dimensions):
                        blockers.add(mapping.criterion_id)
        if report.cv.screening_decision == 'excluded' or positive != scope or concerns or blockers:
            raise HTTPException(422, 'Alignment requires supported scoped requirements without unresolved concerns.')
    elif body.position == 'mixed' and not concerns:
        raise HTTPException(422, 'Missing evidence alone does not establish a concern.')
    elif body.position == 'insufficient' and not gaps:
        raise HTTPException(422, 'Identify the missing or unassessed evidence.')


async def project_confirmation(db, report, job, *, enabled, clock=utc_now):
    if not enabled:
        return ConfirmationView()
    token = evidence_token(report)
    row = await db.scalar(select(Record).where(Record.job_id==report.job_id,
        Record.batch_id==report.batch_id,Record.upload_id==report.upload_id))
    base = dict(enabled=True,evidence_token=token,version=row.version if row else 0)
    if row is None:return ConfirmationView(**base)
    if row.reviewer_id!=job.recruiter_id or digest(row.source_versions)!=row.source_digest:
        return ConfirmationView(**base,state='restricted')
    restricted = row.expires_at <= clock() or (row.scope=='cv_interview' and report.interview.state not in {'available','stale','ambiguous','missing_analysis','pending'})
    if restricted:return ConfirmationView(**base,state='restricted')
    if row.criteria_revision != job.revision or report.criteria_revision != job.revision or not report.confirmed_requirements:
        return ConfirmationView(**base,state='stale')
    if row.scope=='cv_interview' and report.interview.state!='available':return ConfirmationView(**base,state='stale')
    versions = await sources(db,report,row.scope)
    if digest(versions)!=row.source_digest:return ConfirmationView(**base,state='stale')
    try:
        body = ConfirmationInput(expected_version=row.version,evidence_token=token,position=row.position,
            scope=row.scope,requirement_ids=row.requirement_ids,references=row.evidence_references)
        validate_claims(report,body)
    except (ValueError,HTTPException):return ConfirmationView(**base,state='stale')
    return ConfirmationView(**base,state='confirmed',position=body.position,scope=body.scope,
        requirement_ids=body.requirement_ids,references=body.references,reviewer_id=row.reviewer_id,
        confirmed_at=row.confirmed_at,expires_at=row.expires_at)


async def confirm(db,request,owner,job_id,batch_id,upload_id,body,*,storage_enabled,clock=utc_now):
    from app.services.consolidated_assessment import consolidated_assessment
    from app.services.recruiter_records import owned_job
    # Existing reader locks job, then exact interview before any confirmation lock.
    report = await consolidated_assessment(db,request,owner,job_id,batch_id,upload_id,storage_enabled=storage_enabled)
    job = await owned_job(db,owner.id,job_id)
    if report.criteria_revision!=job.revision:raise HTTPException(409,'Review the current confirmed criteria first.')
    row = await db.scalar(select(Record).where(Record.job_id==job_id,Record.batch_id==batch_id,
        Record.upload_id==upload_id).with_for_update().execution_options(populate_existing=True))
    if (row.version if row else 0)!=body.expected_version or body.evidence_token!=evidence_token(report):
        raise HTTPException(409,'Assessment or evidence changed. Refresh before explicitly confirming again.')
    validate_claims(report,body)
    versions = await sources(db,report,body.scope)
    now = clock();expiry = now+timedelta(days=30)
    if body.scope=='cv_interview':expiry = min(expiry,report.interview.retention_deadline)
    if expiry<=now:raise HTTPException(409,'Evidence expired before confirmation.')
    if row is None:
        row=Record(job_id=job_id,batch_id=batch_id,upload_id=upload_id,version=0);db.add(row)
    row.version+=1;row.reviewer_id=owner.id;row.position=body.position;row.scope=body.scope
    row.requirement_ids=body.requirement_ids;row.evidence_references=[r.model_dump(mode='json') for r in body.references]
    row.criteria_revision=job.revision;row.source_versions=versions;row.source_digest=digest(versions)
    row.interview_id=report.interview.interview_id if body.scope=='cv_interview' else None
    row.confirmed_at=now;row.expires_at=expiry
    await db.flush()
    # Commit in the route only after the returned view has also been validated.
    return await project_confirmation(db,report,job,enabled=True,clock=clock)


async def purge_interview_confirmations(db,interview_id):
    # Also runs when serving is disabled and supports pre-0015 installations.
    if await db.scalar(text("SELECT to_regclass('reviewer_confirmations')")):
        await db.execute(delete(Record).where(Record.interview_id==interview_id))
        if await db.scalar(select(Record.id).where(Record.interview_id==interview_id).limit(1)):
            raise RuntimeError('Confirmation cleanup unavailable')


async def sweep_confirmations(db,*,clock=utc_now,limit=100):
    if not await db.scalar(text("SELECT to_regclass('reviewer_confirmations')")):return 0
    from app.db.models.recruiter import InterviewSchedule as Interview,CandidateScoreRecord as Score
    candidates=(await db.scalars(select(Record).outerjoin(Interview,Record.interview_id==Interview.id).where(or_(
        Record.expires_at<=clock(),Interview.transcript_storage_revoked_at.is_not(None),
        Interview.transcript_retention_deadline<=clock(),Interview.transcript_deletion_status!='none',
        ~select(Score.id).where(Score.job_id==Record.job_id,Score.batch_id==Record.batch_id,Score.upload_id==Record.upload_id).exists()
        & ~select(Interview.id).where(Interview.job_id==Record.job_id,Interview.batch_id==Record.batch_id,Interview.upload_id==Record.upload_id).correlate(Record).exists()
        )).order_by(Record.id).limit(limit).with_for_update(of=Record,skip_locked=True))).all()
    for row in candidates:await db.delete(row)
    return len(candidates)
