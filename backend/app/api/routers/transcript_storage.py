"""Consent and read-only transcript review. No client transcript-text ingestion."""
from uuid import UUID
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from app.core.auth import protect_mutation, token_hash
from app.core.config import settings
from app.api.routers.interview_access import candidate_session
from app.api.routers.interview_captions import sessions
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn, TranscriptPrivacyAccess
from app.services.interview_transcripts import transaction, TranscriptError
from app.services.transcript_consent import CONSENT_WORDING, CONSENT_VERSION
from app.services.transcript_privacy import PRIVACY_COOKIE, PRIVACY_PATH
from app.services.transcript_runtime import runtime, maintenance_status

router = APIRouter(tags=['Optional transcript storage'])


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    capture_id: UUID
    decision: Literal['accept','decline']


def enabled():
    if not settings.transcript_storage_enabled:
        raise HTTPException(404, 'Optional transcript storage is disabled.')
    return runtime()


def safe(error):
    return HTTPException(409 if not error.outcome_uncertain else 503,
        {'code':error.code,'outcome_uncertain':error.outcome_uncertain})


@router.get('/transcript-storage/config')
async def configuration():
    return {'enabled':settings.transcript_storage_enabled,'version':CONSENT_VERSION,'wording':CONSENT_WORDING}


async def live_candidate(request, rt):
    async with transaction(rt.storage.factory) as db:
        _, interview = await candidate_session(request, db)
        return interview.id


async def candidate_cookie(rt, request, response, interview):
    raw, expiry = await rt.privacy.issue_candidate_access(request, interview)
    response.set_cookie(PRIVACY_COOKIE,raw,httponly=True,secure=request.url.scheme=='https' or settings.environment!='development',
        samesite='strict',path=PRIVACY_PATH,max_age=max(1,int((expiry-datetime.now(timezone.utc)).total_seconds())))


async def prepare(request, response, interview, job=None):
    rt=enabled()
    try:
        # Storage acceptance must precede capture, avoiding storage of pre-consent audio.
        if interview in sessions and sessions[interview].started is not None:
            raise TranscriptError('storage_consent_requires_new_caption_session')
        result=await rt.coordinator.prepare(request,interview_id=interview,job_id=job)
        if job is None:await candidate_cookie(rt,request,response,interview)
        return {**result,'interview_id':interview}
    except TranscriptError as error:raise safe(error) from None


async def decide(request, response, interview, body, job=None):
    rt=enabled()
    try:
        if body.decision=='accept' and interview in sessions and sessions[interview].started is not None:
            raise TranscriptError('storage_consent_requires_new_caption_session')
        result=await rt.coordinator.decide(request,interview_id=interview,capture_id=body.capture_id,
            decision=body.decision,job_id=job)
        if body.decision=='decline':await rt.privacy.withdraw(request,interview,job)
        if job is None and body.decision=='accept':await candidate_cookie(rt,request,response,interview)
        return result
    except TranscriptError as error:raise safe(error) from None


@router.post('/jobs/{job}/interviews/{interview}/transcript-storage/prepare')
async def recruiter_prepare(job:UUID,interview:UUID,body:Empty,request:Request,response:Response):
    return await prepare(request,response,interview,job)


@router.post('/interview-access/transcript-storage/prepare')
async def candidate_prepare(body:Empty,request:Request,response:Response):
    return await prepare(request,response,await live_candidate(request,enabled()))


@router.post('/jobs/{job}/interviews/{interview}/transcript-storage/decision')
async def recruiter_decide(job:UUID,interview:UUID,body:Decision,request:Request,response:Response):
    return await decide(request,response,interview,body,job)


@router.post('/interview-access/transcript-storage/decision')
async def candidate_decide(body:Decision,request:Request,response:Response):
    return await decide(request,response,await live_candidate(request,enabled()),body)


async def privacy_interview(request,rt):
    async with transaction(rt.storage.factory) as db:
        raw=request.cookies.get(PRIVACY_COOKIE,'')
        access=await db.get(TranscriptPrivacyAccess,token_hash(raw)) if len(raw)==43 else None
        if access and access.expires_at>rt.storage.clock():return access.interview_id
        _, interview=await candidate_session(request,db)
        return interview.id


@router.get('/jobs/{job}/interviews/{interview}/transcript-storage/status')
async def recruiter_status(job:UUID,interview:UUID,request:Request):
    rt=enabled()
    try:return {**(await rt.privacy.status(request,interview,job)),'cleanup_worker':maintenance_status['state']}
    except TranscriptError as error:raise safe(error) from None


@router.get('/interview-transcripts/privacy/status')
async def candidate_privacy_status(request:Request):
    rt=enabled()
    try:return await rt.privacy.status(request,await privacy_interview(request,rt))
    except TranscriptError as error:raise safe(error) from None


@router.post('/jobs/{job}/interviews/{interview}/transcript-storage/withdraw')
async def recruiter_withdraw(job:UUID,interview:UUID,body:Empty,request:Request):
    rt=enabled()
    try:return await rt.privacy.withdraw(request,interview,job)
    except TranscriptError as error:raise safe(error) from None


@router.post('/interview-transcripts/privacy/withdraw')
async def candidate_withdraw(body:Empty,request:Request):
    rt=enabled()
    try:return await rt.privacy.withdraw(request,await privacy_interview(request,rt))
    except TranscriptError as error:raise safe(error) from None


@router.get('/jobs/{job}/interviews/{interview}/transcript')
async def review(job:UUID,interview:UUID,request:Request,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0,le=100000)):
    rt=enabled()
    try:
        async with transaction(rt.storage.factory) as db:
            parent=await rt.privacy._identity(db,request,interview,job)
            await rt.storage._owned(db,parent.recruiter_id,interview)
            rows=(await db.scalars(select(Turn).join(Capture).where(Capture.interview_id==interview)
                .order_by(Capture.started_at,Capture.id,Turn.sequence,Turn.id).limit(limit).offset(offset))).all()
            captures=(await db.scalars(select(Capture).where(Capture.interview_id==interview)
                .order_by(Capture.started_at).limit(100))).all()
            return {'turns':[{'id':r.id,'capture_id':r.session_id,'sequence':r.sequence,
                'role':r.role,'text':r.text,'start_ms':r.start_ms,'end_ms':r.end_ms} for r in rows],
                'captures':[{'id':c.id,'status':c.status,'outcome':c.persistence_outcome,
                    'summary':c.capture_summary} for c in captures],
                'next_offset':offset+len(rows) if len(rows)==limit else None,
                'warning':'Chunk estimates; unverified ASR. Accepted-audio completeness is not full-interview completeness.'}
    except TranscriptError as error:raise safe(error) from None
