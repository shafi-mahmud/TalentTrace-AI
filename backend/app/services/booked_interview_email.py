"""Appointment only: never generate, recover, rotate or email a joining bearer."""
import asyncio
import hashlib
import json
import smtplib
from datetime import timedelta
from zoneinfo import ZoneInfo
from app.services.interview_email import ADDRESS, SMTPTransport


def ready(c):
    return bool(c.interview_email_enabled and c.environment == 'development'
        and c.interview_email_sender and ADDRESS.fullmatch(c.interview_email_sender)
        and c.interview_smtp_host and c.interview_smtp_username and c.interview_smtp_password
        and c.interview_smtp_username.get_secret_value() and c.interview_smtp_password.get_secret_value())


def preview(job, interview, to):
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
        interview.scheduled_at.isoformat(), to, subject, body]
    digest = hashlib.sha256(json.dumps(value, ensure_ascii=True).encode()).hexdigest()
    return {'subject': subject, 'body': body, 'review_digest': digest}


async def dispatch(c, to, subject, body, transport=None):
    try:
        await asyncio.to_thread((transport or SMTPTransport()).send, c, to, subject, body)
        return 'accepted'
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError):
        return 'failed'
    except Exception:
        # Timeout or disconnect can occur after DATA acceptance. Never retry.
        return 'uncertain'
