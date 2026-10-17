"""Text-only retention/deletion. No audio, content logging or external providers."""
import secrets
from datetime import timedelta
from sqlalchemy import select, delete, func, or_, DateTime, text
from fastapi import HTTPException
from app.core.auth import current_recruiter, protect_mutation, token_hash
from app.api.routers.interview_access import candidate_session
from app.db.models.recruiter import InterviewSchedule
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn, TranscriptPrivacyAccess
from app.services.interview_transcripts import transaction, TranscriptError

PRIVACY_COOKIE = 'talenttrace_transcript_privacy'
PRIVACY_PATH = '/api/v1/interview-transcripts/privacy'


class TranscriptPrivacyService:
    def __init__(self, persistence):
        self.storage = persistence
        self.factory, self.clock = persistence.factory, persistence.clock
        self._cleanup_after = None  # Fair bounded scan, never an authorization cache.

    async def _identity(self, db, request, interview_id, job_id=None):
        await protect_mutation(request)
        if job_id is not None:
            user = await current_recruiter(request, db)
            row = await self.storage._owned(db, user.id, interview_id, storage=False)
            if row.job_id != job_id:
                raise TranscriptError('owned_interview_not_found')
            return row
        raw = request.cookies.get(PRIVACY_COOKIE, '')
        access = await db.get(TranscriptPrivacyAccess, token_hash(raw)) if len(raw) == 43 else None
        if access and access.interview_id == interview_id and access.expires_at > self.clock():
            interview = await db.get(InterviewSchedule, interview_id)
            # A valid candidate's deletion right outlives owner-account activity.
            # This boundary returns privacy status only, never transcript text.
            return await self._cleanup_owned(db, interview.recruiter_id, interview_id)
        _, interview = await candidate_session(request, db)
        if interview.id != interview_id:
            raise TranscriptError('privacy_access_unavailable')
        return await self.storage._owned(db, interview.recruiter_id, interview_id, storage=False)

    async def issue_candidate_access(self, request, interview_id):
        # Issuance uses the existing live participant boundary and open window.
        async with transaction(self.factory) as db:
            _, _, interview = await self.storage.authority._participant(db, request, interview_id=interview_id)
            deadline = interview.transcript_retention_deadline or min(self.clock(),
                interview.scheduled_at + timedelta(minutes=interview.duration_minutes)) + timedelta(days=30)
            raw = request.cookies.get(PRIVACY_COOKIE, '')
            old = await db.get(TranscriptPrivacyAccess, token_hash(raw)) if len(raw) == 43 else None
            if old and old.interview_id == interview_id and old.expires_at > self.clock():
                return raw, old.expires_at
            # Keep prior privacy capabilities valid across invitation rotation.
            # Bound issuance without invalidating a participant's deletion rights.
            await db.execute(delete(TranscriptPrivacyAccess).where(
                TranscriptPrivacyAccess.interview_id == interview_id,
                TranscriptPrivacyAccess.expires_at <= self.clock()))
            count = await db.scalar(select(func.count()).select_from(TranscriptPrivacyAccess).where(
                TranscriptPrivacyAccess.interview_id == interview_id))
            if count >= 20:
                raise TranscriptError('privacy_access_capacity_unavailable')
            raw = secrets.token_urlsafe(32)
            expires = deadline + timedelta(days=1)
            db.add(TranscriptPrivacyAccess(token_hash=token_hash(raw),interview_id=interview_id,expires_at=expires))
        return raw, expires

    async def status(self, request, interview_id, job_id=None):
        async with transaction(self.factory) as db:
            row = await self._identity(db, request, interview_id, job_id)
            view = self.view(row)
            capture = await db.scalar(select(Capture).where(Capture.interview_id == row.id)
                .order_by(Capture.started_at.desc()).limit(1))
            view.update(capture_status=capture.status if capture else None,
                persistence_outcome=capture.persistence_outcome if capture else None,
                capture_summary=capture.capture_summary if capture else None)
            return view

    def view(self, row):
        return {'withdrawn': row.transcript_storage_revoked_at is not None,
            'expired': row.transcript_retention_deadline is not None and self.clock() >= row.transcript_retention_deadline,
            'retention_deadline': row.transcript_retention_deadline,
            'deletion_status': row.transcript_deletion_status,
            'deletion_verified': row.transcript_deletion_status == 'deleted' and row.transcript_deleted_at is not None}

    async def withdraw(self, request, interview_id, job_id=None):
        # Revoke and commit BEFORE physical deletion. No join-window requirement.
        async with transaction(self.factory) as db:
            row = await self._identity(db, request, interview_id, job_id)
            owner = row.recruiter_id
            if row.transcript_storage_revoked_at is None:
                row.transcript_storage_revoked_at = self.clock()
            if row.transcript_deletion_status != 'deleted':
                row.transcript_deletion_status = 'pending'
        try:
            await self.delete_revoked(owner, interview_id)
        except TranscriptError:
            # Never report physical deletion as complete on failure/uncertainty.
            pass
        return await self.status(request, interview_id, job_id)

    async def _cleanup_owned(self, db, owner, interview_id):
        # Internal deletion must remain possible when the owner account is inactive.
        # Public callers authenticate through _identity; sweep derives owner in DB.
        row = await db.scalar(select(InterviewSchedule).where(
            InterviewSchedule.id == interview_id, InterviewSchedule.recruiter_id == owner)
            .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise TranscriptError('owned_interview_not_found')
        return row

    async def delete_revoked(self, owner, interview_id):
        try:
            async with transaction(self.factory) as db:
                row = await self._cleanup_owned(db, owner, interview_id)
                expired = row.transcript_retention_deadline is not None and self.clock() >= row.transcript_retention_deadline
                if row.transcript_storage_revoked_at is None:
                    if not expired:
                        raise TranscriptError('deletion_not_authorized')
                    row.transcript_storage_revoked_at = self.clock()
                if row.transcript_deletion_status != 'deleted':
                    row.transcript_deletion_status = 'pending'
            # Fence and pending status commit independently of physical deletion.
            async with transaction(self.factory) as db:
                row = await self._cleanup_owned(db, owner, interview_id)
                if row.transcript_storage_revoked_at is None:
                    raise TranscriptError('deletion_not_authorized')
                captures = select(Capture.id).where(Capture.interview_id == interview_id)
                from app.services.reviewer_confirmation import purge_interview_confirmations
                try:
                    await purge_interview_confirmations(db,interview_id)
                except Exception:
                    raise TranscriptError('deletion_unverified') from None
                # Cleanup also works when analysis serving is disabled. Legacy 0013
                # installations have no derived table; never assume a feature flag
                # means previously saved sensitive text no longer needs deletion.
                if await db.scalar(text("SELECT to_regclass('interview_analyses')")):
                    from app.db.models.interview_analysis import InterviewAnalysis
                    await db.execute(delete(InterviewAnalysis).where(InterviewAnalysis.interview_id==interview_id))
                    if await db.scalar(select(func.count()).select_from(InterviewAnalysis).where(InterviewAnalysis.interview_id==interview_id)):
                        raise TranscriptError('deletion_unverified')
                await db.execute(delete(Turn).where(Turn.session_id.in_(captures)))
                await db.execute(delete(Capture).where(Capture.interview_id == interview_id))
                remaining = await db.scalar(select(func.count()).select_from(Capture).where(Capture.interview_id == interview_id))
                if remaining:
                    raise TranscriptError('deletion_unverified')
                row.transcript_deletion_status = 'deleted'
                row.transcript_deleted_at = row.transcript_deleted_at or self.clock()
        except TranscriptError as error:
            # An expired deadline already denies reads even if this audit update fails.
            if error.code != 'deletion_not_authorized':
                try:
                    async with transaction(self.factory) as db:
                        row = await self._cleanup_owned(db, owner, interview_id)
                        if row.transcript_deletion_status != 'deleted':
                            row.transcript_deletion_status = 'failed'
                except TranscriptError:
                    pass
            raise

    async def sweep(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise TranscriptError('invalid_cleanup_bound')
        async with transaction(self.factory) as db:
            query = select(InterviewSchedule).where(
                or_(InterviewSchedule.transcript_retention_deadline <= self.clock(),
                    InterviewSchedule.transcript_storage_revoked_at.is_not(None)),
                InterviewSchedule.transcript_deletion_status != 'deleted')
            page = query.where(InterviewSchedule.id > self._cleanup_after) if self._cleanup_after else query
            rows = (await db.scalars(page.order_by(InterviewSchedule.id).limit(limit)
                .with_for_update(skip_locked=True))).all()
            if not rows and self._cleanup_after is not None:
                rows = (await db.scalars(query.order_by(InterviewSchedule.id).limit(limit)
                    .with_for_update(skip_locked=True))).all()
            targets = [(row.recruiter_id, row.id) for row in rows]
            for row in rows:
                row.transcript_storage_revoked_at = row.transcript_storage_revoked_at or self.clock()
                row.transcript_deletion_status = 'pending'
        self._cleanup_after = targets[-1][1] if targets else None
        failed = 0
        for owner, interview in targets:
            try: await self.delete_revoked(owner, interview)
            except TranscriptError: failed += 1
        return {'processed': len(targets), 'failed': failed}

    async def interrupt_stale(self, limit=20):
        # Existing caption capture is bounded to <=300s plus 35s finalization.
        # Ten-minute stale sessions cannot be active supported caption captures.
        async with transaction(self.factory) as db:
            origin = func.coalesce(Capture.capture_summary['recognition_started_at'].astext.cast(DateTime(timezone=True)),Capture.started_at)
            old = select(Capture.interview_id).where(Capture.status == 'active',
                origin <= self.clock()-timedelta(minutes=10))
            parents = (await db.scalars(select(InterviewSchedule).where(InterviewSchedule.id.in_(old))
                .limit(limit).with_for_update(skip_locked=True))).all()
            for parent in parents:
                captures = (await db.scalars(select(Capture).where(Capture.interview_id == parent.id,
                    Capture.status == 'active', origin <= self.clock()-timedelta(minutes=10))
                    .with_for_update())).all()
                for capture in captures:
                    count = await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id == capture.id))
                    capture.status, capture.ended_at = 'interrupted', self.clock()
                    capture.persistence_outcome = 'partial' if count else 'failed'
                    # Unknown in-memory samples cannot be reconstructed after restart.
                    capture.capture_summary = None
