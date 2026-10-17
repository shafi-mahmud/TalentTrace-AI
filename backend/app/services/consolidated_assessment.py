"""Read-only candidate identity join. Never construct an evaluation manager/provider."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.recruiter import CandidateScoreRecord, InterviewSchedule
from app.db.models.interview_analysis import InterviewAnalysis
from app.schemas.consolidated_assessment import ConsolidatedAssessment, InterviewEvidence
from app.services.recruiter_records import owned_job
from app.services.score_records import SCORING_VERSION, restore_candidate_score
from app.services.evaluation_input import PostInterviewInputService, EvaluationInputError
from app.services.interview_transcripts import TranscriptPersistenceService, TranscriptError, utc_now
from app.services.interview_analysis import fingerprint
from app.services.interview_qa import QAPair, validate_pairs, pair_transcript
from app.services.interview_mapping import TechnicalReference, map_requirements
from app.agents.evaluation.workflow import ModelAssessment, validate_assessment, RUBRIC_VERSION, AssessmentError


def checked_cv(payload, job, upload_id):
    score = restore_candidate_score(payload)
    if score.job_reference != job.job_reference or score.upload_id != upload_id:
        raise ValueError('Invalid saved association')
    return score


def checked_result(row, source):
    """Revalidate persisted source/quotes and expose only a typed projection."""
    result = row.result
    if (row.input_digest != fingerprint(source) or row.rubric_version != RUBRIC_VERSION
            or result['rubric_version'] != row.rubric_version
            or result['criteria_revision'] != source.criteria_revision
            or result['advisory'] is not True or result['scope'] != source.scope
            or result['asr_review'] != source.asr_review
            or result['turns'] != [t.model_dump(mode='json') for t in source.turns]):
        raise ValueError('Stored source association changed')
    pairs = tuple(QAPair.model_validate_json(json.dumps(p)) for p in result['pairs'])
    references = tuple(TechnicalReference.model_validate_json(json.dumps(r)) for r in result['technical_references'])
    if not 1 <= len(pairs) <= 50 or len(references) > 10:
        raise ValueError('Unbounded persisted result')
    validate_pairs(source, pairs)
    if pairs != pair_transcript(source):
        raise ValueError('Stored pairing association changed')
    mappings = map_requirements(source, pairs)
    if result['requirements'] != [m.model_dump(mode='json') for m in mappings]:
        raise ValueError('Stored coverage association changed')
    assessment = validate_assessment(source, pairs, references, ModelAssessment.model_validate(result['assessment']))
    return InterviewEvidence(state='available', interview_id=source.interview_id, operation_id=row.id,
        rubric_version=row.rubric_version, retention_deadline=source.retention_deadline, warning=source.warning, pairs=pairs,
        requirements=mappings, assessment=assessment, references=references, turns=source.turns)


async def interview_evidence(db, request, job, interview, *, storage_enabled, clock=utc_now):
    def status(state):
        return InterviewEvidence(state=state, interview_id=interview.id)
    # Parent lock is acquired by the caller before inspecting any derived text.
    if interview.transcript_storage_revoked_at is not None:
        return status('withdrawn')
    if interview.transcript_retention_deadline is not None and clock() >= interview.transcript_retention_deadline:
        return status('expired')
    if interview.transcript_deletion_status != 'none' or interview.transcript_deleted_at is not None:
        return status('deleted' if interview.transcript_deletion_status == 'deleted' else 'unavailable')
    if interview.criteria_revision != job.revision or job.confirmed_snapshot is None:
        return status('stale')
    if not storage_enabled:
        return status('disabled')
    rows = (await db.scalars(select(InterviewAnalysis).where(
        InterviewAnalysis.interview_id == interview.id, InterviewAnalysis.job_id == job.id,
        InterviewAnalysis.recruiter_id == request.state.recruiter_id,
        InterviewAnalysis.criteria_revision == job.revision).limit(21))).all()
    if not rows:
        return status('missing_analysis')
    if len(rows) > 20:
        return status('unavailable')
    # Reuse the source consent/completeness/retention boundary in this transaction.
    storage = TranscriptPersistenceService(None, None, clock=clock)
    try:
        source = await PostInterviewInputService(storage).load(db, request,
            job_id=job.id, interview_id=interview.id, revision=job.revision)
        matching = [r for r in rows if r.input_digest == fingerprint(source)]
        if not matching:
            return status('stale')
        completed = [r for r in matching if r.status == 'completed']
        if len(completed) > 1:
            return status('ambiguous')  # Never silently choose a model/corpus variant.
        if completed:
            return checked_result(completed[0], source)
        return status('pending' if any(r.status == 'running' and r.lease_expires_at > clock() for r in matching) else 'unavailable')
    except (TranscriptError, EvaluationInputError, AssessmentError, ValueError, TypeError, KeyError, AttributeError):
        return status('unavailable')  # Never leak text or private exception details.


def persisted_cv(job, upload_id, *, row=None, interview=None):
    """Shared CV association/selection validation; never reconstruct lost evidence."""
    payload = interview.screening_snapshot if interview else row.payload
    try:
        cv = checked_cv(payload, job, upload_id)
        if interview and (interview.scoring_version != SCORING_VERSION or cv.screening_decision != 'eligible'
                or cv.status != 'scored' and cv.reason not in {'uncertain_evidence', 'missing_dimension_criteria'}):
            raise ValueError('Invalid interview selection')
        if not interview and (cv.score != row.score or job.confirmed_snapshot is None
                or cv.weights.model_dump() != job.scoring_weights):
            raise ValueError('Invalid stored score')
        return cv
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(409, 'Saved candidate assessment is unavailable.') from None


async def consolidated_assessment(db, request, owner, job_id, batch_id, upload_id, *, storage_enabled):
    # Same exact job/batch/upload identity used when selecting an interview.
    job = await owned_job(db, owner.id, job_id, lock=True)
    interview = await db.scalar(select(InterviewSchedule).where(
        InterviewSchedule.job_id == job.id, InterviewSchedule.recruiter_id == owner.id,
        InterviewSchedule.batch_id == batch_id, InterviewSchedule.upload_id == upload_id)
        .with_for_update().execution_options(populate_existing=True))
    if interview:
        revision, origin = interview.criteria_revision, 'interview_selection_snapshot'
    else:
        row = await db.scalar(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id == job.id,
            CandidateScoreRecord.batch_id == batch_id, CandidateScoreRecord.upload_id == upload_id,
            CandidateScoreRecord.criteria_revision == job.revision,
            CandidateScoreRecord.scoring_version == SCORING_VERSION))
        if row is None:
            raise HTTPException(404, 'Saved candidate assessment not found.')
        revision, origin = row.criteria_revision, 'current_saved_score'
    cv = persisted_cv(job, upload_id, row=None if interview else row, interview=interview)
    evidence = (await interview_evidence(db, request, job, interview, storage_enabled=storage_enabled)
                if interview else InterviewEvidence(state='not_scheduled'))
    report = ConsolidatedAssessment(job_id=job.id, job_title=job.job_title, job_reference=job.job_reference,
        batch_id=batch_id, upload_id=upload_id, criteria_revision=revision,
        cv_source=origin, cv=cv, confirmed_requirements=report_requirements(job, revision, cv), interview=evidence)
    from app.core.config import settings
    from app.services.reviewer_confirmation import project_confirmation
    view = await project_confirmation(db, report, job,
        enabled=settings.reviewer_confirmation_enabled and settings.environment=='development')
    return report.model_copy(update={'confirmation': view})


def report_requirements(job, revision, cv):
    """Read names only from the exact confirmed revision; no historical guessing."""
    from app.schemas.batch_screening import ReviewedJobSnapshot
    if revision != job.revision or job.confirmed_snapshot is None:
        return ()
    try:
        snapshot = ReviewedJobSnapshot.model_validate(job.confirmed_snapshot)
        if snapshot.job_reference != job.job_reference:
            return ()
        by_id = {c.criterion_id: c for c in snapshot.criteria}
        for dimension in cv.dimensions:
            for match in dimension.matches:
                criterion = by_id.get(match.criterion_id)
                if criterion is None or criterion.category != dimension.category:
                    return ()
        return tuple(snapshot.criteria)
    except (ValueError, TypeError, AttributeError, KeyError):
        return ()


async def compare_assessments(db, request, owner, job_id, selections, *, storage_enabled):
    from app.schemas.consolidated_assessment import CandidateComparison
    # One owned job lock stabilizes criteria/weights across both reads. The shared
    # report reader retains interview locks until this request transaction closes.
    job = await owned_job(db, owner.id, job_id, lock=True)
    if job.confirmed_snapshot is None:
        raise HTTPException(409, 'Comparison requires current confirmed job criteria.')
    if len(selections) != 2 or selections[0] == selections[1]:
        raise HTTPException(422, 'Select two distinct applications from the same job.')
    reports = []
    for batch_id, upload_id in selections:
        reports.append(await consolidated_assessment(db, request, owner, job_id, batch_id, upload_id,
            storage_enabled=storage_enabled))
    if any(r.criteria_revision != job.revision or r.cv.weights.model_dump() != job.scoring_weights for r in reports):
        raise HTTPException(409, 'Comparison requires the current confirmed criteria revision and weights.')
    # Time can advance while the second report is read, even under row locks.
    for index, report in enumerate(reports):
        deadline = report.interview.retention_deadline
        if report.interview.state == 'available' and deadline is not None and utc_now() >= deadline:
            reports[index] = report.model_copy(update={'interview': InterviewEvidence(
                state='expired', interview_id=report.interview.interview_id)})
        if reports[index].confirmation.state=='confirmed' and (
                reports[index].confirmation.expires_at<=utc_now() or
                reports[index].confirmation.scope=='cv_interview' and reports[index].interview.state!='available'):
            from app.schemas.reviewer_confirmation import ConfirmationView
            reports[index]=reports[index].model_copy(update={'confirmation':ConfirmationView(
                enabled=report.confirmation.enabled,state='restricted',version=report.confirmation.version)})
    return CandidateComparison(job_id=job.id, criteria_revision=job.revision, reports=tuple(reports))
