"""Consent-only integration; synthetic identities, no STT, audio or text writer."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.services.interview_transcripts import StorageConsentAuthority, TranscriptError
from app.services.transcript_consent import (
    TranscriptConsentCoordinator, CONSENT_VERSION, CONSENT_WORDING,
)


def setup():
    now = [datetime.now(timezone.utc)]
    owner, actor, interview, job = uuid4(), uuid4(), uuid4(), uuid4()
    authority = StorageConsentAuthority(None, version=CONSENT_VERSION, clock=lambda: now[0])

    async def participant(request, *, interview_id, job_id=None):
        role = request.headers.get('test-role')
        if interview_id != interview or role not in ('recruiter', 'candidate'):
            raise TranscriptError('storage_consent_not_verified')
        if (job_id == job) != (role == 'recruiter'):
            raise TranscriptError('storage_consent_not_verified')
        return role, owner if role == 'recruiter' else actor, owner

    authority.participant = AsyncMock(side_effect=participant)
    persistence = N(authority=authority, create_session=AsyncMock(), finish_session=AsyncMock(), append_final=AsyncMock())
    coordinator = TranscriptConsentCoordinator(authority, persistence)

    def request(role='recruiter', version=CONSENT_VERSION):
        return Request({'type':'http','method':'POST','headers':[
            (b'test-role',role.encode()),(b'x-talenttrace-storage-consent',version.encode())]})

    async def prepare():
        return await coordinator.prepare(request(), interview_id=interview, job_id=job)

    async def decide(capture, role='recruiter', decision='accept', **patch):
        return await coordinator.decide(request(role), **dict(dict(interview_id=interview,
            capture_id=capture, decision=decision, job_id=job if role=='recruiter' else None), **patch))

    return N(**locals())


def test_independent_consent_duplicates_and_no_transcript_writer():
    async def run():
        f=setup(); view=await f.prepare(); capture=view['capture_id']
        assert view['wording']==CONSENT_WORDING
        assert (await f.prepare())['capture_id']==capture
        assert (await f.decide(capture))['status']=='awaiting_consent'
        # Recruiter cannot submit a role field to stand in for the candidate.
        assert (await f.decide(capture))['status']=='awaiting_consent'
        f.persistence.create_session.assert_not_awaited()
        view=await f.decide(capture,'candidate')
        assert view['status']=='authorized_session_no_transcript'
        assert not view['transcript_saved'] and not view['transcript_writing_enabled']
        first=f.persistence.create_session.call_args
        await f.decide(capture,'candidate')
        assert f.persistence.create_session.call_args==first  # Identical HMAC receipts/timestamps.
        assert first.args[3].role=='recruiter' and first.args[4].role=='candidate'
        f.persistence.append_final.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize('decision',['decline','withdraw'])
def test_refusal_preserves_caption_independence_and_blocks_reacceptance(decision):
    async def run():
        f=setup(); capture=(await f.prepare())['capture_id'];await f.decide(capture)
        view=await f.decide(capture,'candidate',decision)
        assert view['status'] in ('declined','withdrawn')
        assert not view['deletion_verified'] and not view['durable_revocation_enforced']
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await f.decide(capture)
        f.persistence.create_session.assert_not_awaited()
        # No dependency or callback into CaptionSession exists.
        from app.services.interview_captions import CaptionSession
        worker=N(start=AsyncMock(),close=AsyncMock())
        session=CaptionSession(lambda:worker)
        await session.connect('recruiter',AsyncMock());await session.connect('candidate',AsyncMock())
        await session.approve('recruiter');await session.approve('candidate')
        assert session.started is not None and not session.stopped
        await session.stop()
    asyncio.run(run())


@pytest.mark.parametrize('failure',['capture','interview','unauthorized','impersonation','version','expired','tampered'])
def test_invalid_identity_receipt_and_access_are_rejected(failure):
    async def run():
        f=setup();capture=(await f.prepare())['capture_id']
        if failure=='expired':
            await f.decide(capture);f.now[0]+=timedelta(minutes=6)
        if failure=='tampered':
            await f.decide(capture)
            entry=f.coordinator._entries[f.interview]
            entry.receipts['recruiter']=replace(entry.receipts['recruiter'],actor_id=uuid4())
        with pytest.raises(TranscriptError):
            if failure=='capture': await f.decide(uuid4())
            elif failure=='interview': await f.decide(capture,interview_id=uuid4())
            elif failure=='unauthorized': await f.decide(capture,'visitor')
            elif failure=='impersonation': await f.decide(capture,job_id=None)
            elif failure=='version':
                await f.coordinator.decide(f.request(version='unapproved'),interview_id=f.interview,
                    capture_id=capture,job_id=f.job,decision='accept')
            else: await f.decide(capture,'candidate')
        f.persistence.create_session.assert_not_awaited()
    asyncio.run(run())


def test_withdrawal_serializes_with_creation_and_revokes_both_receipts():
    async def run():
        f=setup();capture=(await f.prepare())['capture_id'];await f.decide(capture)
        entered,release=asyncio.Event(),asyncio.Event()
        async def create(*args): entered.set();await release.wait()
        f.persistence.create_session.side_effect=create
        accepting=asyncio.create_task(f.decide(capture,'candidate'))
        await entered.wait()
        withdrawal=asyncio.create_task(f.decide(capture,decision='withdraw'))
        await asyncio.sleep(0);assert not withdrawal.done()
        release.set();await accepting
        view=await withdrawal
        assert view['status']=='withdrawn' and not view['session_closure_pending']
        f.persistence.finish_session.assert_awaited_once_with(f.owner,capture,completed=False)
        for receipt in f.persistence.create_session.call_args.args[3:]:
            with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
                f.authority.verify(receipt,capture_id=capture,interview_id=f.interview,role=receipt.role)
        f.persistence.append_final.assert_not_awaited()
    asyncio.run(run())


def test_uncertain_creation_and_failed_closure_do_not_restore_authorization_or_retry():
    async def run():
        f=setup();capture=(await f.prepare())['capture_id'];await f.decide(capture)
        f.persistence.create_session.side_effect=TranscriptError('transcript_storage_unavailable',outcome_uncertain=True)
        with pytest.raises(TranscriptError) as error:await f.decide(capture,'candidate')
        assert error.value.outcome_uncertain
        f.persistence.create_session.assert_awaited_once()
        f.persistence.finish_session.side_effect=TranscriptError('transcript_storage_unavailable')
        with pytest.raises(TranscriptError):await f.decide(capture,decision='withdraw')
        view=await f.prepare()
        assert view['status']=='withdrawn' and view['session_closure_pending']
        with pytest.raises(TranscriptError):await f.decide(capture)
        # Explicit caller retry only, no automatic cleanup/deletion claim.
        f.persistence.finish_session.side_effect=None
        assert not (await f.decide(capture,decision='withdraw'))['session_closure_pending']
    asyncio.run(run())


def test_bounded_entries_and_unregistered_integration():
    async def run():
        f=setup();f.coordinator._entries={uuid4():None for _ in range(100)}
        with pytest.raises(TranscriptError,match='storage_consent_capacity_unavailable'):await f.prepare()
    asyncio.run(run())
    from app.main import app
    assert not any('storage-consent' in getattr(route,'path','') for route in app.routes)
