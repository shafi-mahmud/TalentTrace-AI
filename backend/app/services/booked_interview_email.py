"""Appointment only: never generate, recover, rotate or email a joining bearer."""
import asyncio
import smtplib
from datetime import timedelta
from zoneinfo import ZoneInfo
from app.services.interview_email import ADDRESS, SMTPTransport
from app.services.bulk_scheduling import masked, contact_fact, digest
from app.schemas.external_cv import ApplicationContact, SourceId, SubmissionId
from app.schemas.cv_upload import JobReference
from app.db.models.external_cv import ExternalCvSubmissionRecord
from pydantic import TypeAdapter
from fastapi import HTTPException
from sqlalchemy import select


async def review_contact(session, job, interview, to):
    # The intake ledger has a unique batch/upload pair. Never search by name,
    # CV content, recipient address or browser-provided provenance.
    rows = (await session.scalars(select(ExternalCvSubmissionRecord).where(
        ExternalCvSubmissionRecord.batch_id == interview.batch_id,
        ExternalCvSubmissionRecord.upload_id == interview.upload_id).limit(2)
        .execution_options(populate_existing=True))).all()
    if not rows:
        return None  # Native upload: manually addressed, not a source contact claim.
    try:
        if len(rows) != 1:
            raise ValueError()
        row = rows[0]
        if row.job_id != job.id or row.status != 'pending_review':
            raise ValueError()
        TypeAdapter(SourceId).validate_python(row.source_id)
        TypeAdapter(SubmissionId).validate_python(row.external_submission_id)
        # Bridge source reference may legitimately differ from the target job.
        TypeAdapter(JobReference).validate_python(row.source_job_reference)
        checked = ApplicationContact(email=row.application_email, status=row.contact_status,
            provenance=row.email_provenance, collection_type=row.email_collection_type,
            validation_version=row.contact_validation_version)
        if checked.status != 'available' or checked.email.casefold() != to.casefold():
            raise ValueError()
    except Exception:
        raise HTTPException(409, 'Recorded application contact is unavailable or does not match. Review the trusted intake record.') from None
    return {**contact_fact(row), 'batch_id': row.batch_id, 'upload_id': row.upload_id,
        'status': row.status}



def ready(c):
    return bool(c.interview_email_enabled and c.environment == 'development'
        and c.interview_email_sender and ADDRESS.fullmatch(c.interview_email_sender)
        and c.interview_smtp_host and c.interview_smtp_username and c.interview_smtp_password
        and c.interview_smtp_username.get_secret_value() and c.interview_smtp_password.get_secret_value())


def preview(job, interview, to, contact=None):
    start = interview.scheduled_at.astimezone(ZoneInfo(interview.timezone))
    end = (interview.scheduled_at + timedelta(minutes=interview.duration_minutes)).astimezone(ZoneInfo(interview.timezone))
    subject = 'Synthetic interview appointment confirmation'
    body = (f'Job Reference: {job.job_reference}\nApplication reference: {interview.upload_id}\n'
        f'Start: {start:%d %B %Y %H:%M} ({interview.timezone})\n'
        f'End: {end:%d %B %Y %H:%M} ({interview.timezone})\n'
        f'Duration: {interview.duration_minutes} minutes\n'
        'Appointment confirmation only. This email provides no joining link or interview access. '
        'The recruiter must arrange joining access separately before the interview.')
    # Binds the reviewed recipient and saved record, including criteria and batch.
    value = [str(interview.id), str(interview.batch_id), interview.criteria_revision,
        interview.scheduled_at.isoformat(), to, subject, body, contact]
    return {'subject': subject, 'body': body, 'review_digest': digest(value),
        'contact_status': 'matches_recorded' if contact else 'no_recorded_contact',
        'recipient_mask': masked(to)}


async def dispatch(c, to, subject, body, transport=None):
    try:
        await asyncio.to_thread((transport or SMTPTransport()).send, c, to, subject, body)
        return 'accepted'
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError):
        return 'failed'
    except Exception:
        # Timeout or disconnect can occur after DATA acceptance. Never retry.
        return 'uncertain'
