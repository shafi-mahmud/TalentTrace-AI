"""Loopback, disposable browser rehearsal. Never seeds transcript turns.

Synthetic saved eligibility is a test fixture, not a live CV-screening claim.
The interview is created through the normal authenticated scheduling API.
"""
import argparse
import asyncio
from datetime import datetime,timedelta,timezone
import json
import math
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))


def valid_lifetime(runtime_seconds,interview_minutes):
    return (type(runtime_seconds) is int and 60<=runtime_seconds<=7200
        and type(interview_minutes) is int and 30<=interview_minutes<=180
        and runtime_seconds<=interview_minutes*60)


async def serve(args):
    import httpx
    import uvicorn
    from dotenv import dotenv_values
    from pydantic import SecretStr
    from sqlalchemy import delete
    from test_interview_transcripts import pg,fixture
    from test_candidate_scoring import scored
    from app.schemas.candidate_score import ScoringWeights
    from app.core.config import settings
    from app.core.auth import hash_password,session_factory
    from app.db.models.recruiter import Recruiter,JobProfile,CandidateScoreRecord,InterviewInvitation,InterviewSchedule
    values=dotenv_values(args.env_file)
    if not values.get('GROQ_API_KEY') or not values.get('LLM_MODEL'):raise RuntimeError('Provider configuration missing')
    if not Path(args.whisper_model).is_dir():raise RuntimeError('Local model unavailable')
    generator=pg.__wrapped__();url=next(generator);f=None
    try:
        f=await fixture(url)
        settings.database_url=SecretStr(url.render_as_string(hide_password=False))
        settings.environment='development';settings.cors_origins=['http://127.0.0.1:5190']
        settings.interview_email_enabled=False
        settings.livekit_synthetic_demo_enabled=True;settings.livekit_local_development_enabled=True
        settings.livekit_url=SecretStr('ws://127.0.0.1:7880')
        # Official --dev server credentials, loopback only; never a deployed secret.
        settings.livekit_api_key=SecretStr('devkey');settings.livekit_api_secret=SecretStr('secret')
        settings.local_caption_model_path=Path(args.whisper_model)
        settings.transcript_storage_enabled=True;settings.interview_evaluation_enabled=True
        settings.interview_evaluation_durable_enabled=True
        settings.interview_evaluation_synthetic_job_ids=[f.job]
        settings.groq_api_key=SecretStr(values['GROQ_API_KEY']);settings.llm_model=values['LLM_MODEL']
        session_factory.cache_clear()
        weights=ScoringWeights(skill=100,experience=0,education=0)
        score,_,_=await asyncio.to_thread(scored,['supported'],weights=weights)
        batch=uuid4();password=secrets.token_urlsafe(24)
        async with f.factory.begin() as db:
            # Remove only the helper's unused disposable interview; no transcript exists.
            await db.execute(delete(InterviewInvitation).where(InterviewInvitation.interview_id==f.interview))
            await db.execute(delete(InterviewSchedule).where(InterviewSchedule.id==f.interview))
            user=await db.get(Recruiter,f.owner);email=user.email;user.password_hash=hash_password(password)
            job=await db.get(JobProfile,f.job)
            score=score.model_copy(update={'job_reference':job.job_reference})
            job.job_title='Synthetic Python interview rehearsal'
            criteria=[dict(criterion_id='python',category='skill',description='Python',is_hard=False)]
            job.suggestions={'job_title':job.job_title,'criteria':criteria}
            job.confirmed_snapshot={'job_reference':job.job_reference,'job_title':job.job_title,'criteria_confirmed':True,'criteria':criteria}
            db.add(CandidateScoreRecord(id=uuid4(),job_id=job.id,batch_id=batch,upload_id=score.upload_id,
                criteria_revision=2,scoring_version='f2-coverage-v1',score=score.score,payload=score.model_dump(mode='json')))
        from app.main import app
        from fastapi.middleware.cors import CORSMiddleware
        for middleware in app.user_middleware:
            if middleware.cls is CORSMiddleware:middleware.kwargs['allow_origins']=settings.cors_origins
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8022',
            headers={'X-TalentTrace-Request':'1','cookie':dict(f.request().headers)['cookie']}) as client:
            scheduled=await client.post(f'/api/v1/jobs/{f.job}/interviews',json={
                'batch_id':str(batch),'upload_id':str(score.upload_id),'criteria_revision':2,
                'selection_confirmed':True,'scheduled_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
                'timezone':'Asia/Dhaka','duration_minutes':args.interview_duration_minutes})
            if scheduled.status_code!=201:raise RuntimeError('Normal scheduling refused synthetic fixture')
            interview=scheduled.json()['id']
            invitation=await client.post(f'/api/v1/jobs/{f.job}/interviews/{interview}/invitation',
                json={'expires_in_hours':math.ceil(args.interview_duration_minutes/60)+1})
            if invitation.status_code!=200:raise RuntimeError('Invitation creation failed')
        private=ROOT/'data/milestone3';private.mkdir(parents=True,exist_ok=True)
        (private/'LOGIN.txt').write_text(email+'\n'+password+'\n')
        (private/'LIVE-TARGETS.json').write_text(json.dumps({'job':str(f.job),'interview':interview,
            'candidate_url':'http://127.0.0.1:5190/interview-join#invite='+invitation.json()['token']}))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8022,access_log=False,log_level='critical'))
        async def deadline():await asyncio.sleep(args.max_runtime_seconds);server.should_exit=True
        timer=asyncio.create_task(deadline())
        print('Live disposable rehearsal ready on 8022; private LOGIN.txt and LIVE-TARGETS.json are in ignored data/milestone3. No transcript or inference seeded.',flush=True)
        print('Automatic shutdown: '+(datetime.now(timezone.utc)+timedelta(seconds=args.max_runtime_seconds)).isoformat()+
            '; disposable data is removed at shutdown.',flush=True)
        try:await server.serve()
        finally:timer.cancel()
    finally:
        if f:await f.engine.dispose()
        try:next(generator)
        except StopIteration:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',required=True)
    parser.add_argument('--whisper-model',required=True)
    parser.add_argument('--confirm-free-tier-synthetic',action='store_true')
    parser.add_argument('--max-runtime-seconds',type=int,default=1800)
    parser.add_argument('--interview-duration-minutes',type=int,default=30)
    args=parser.parse_args()
    if not args.confirm_free_tier_synthetic or Path.cwd()!=ROOT/'backend' or not valid_lifetime(args.max_runtime_seconds,args.interview_duration_minutes):
        parser.error('Explicit synthetic confirmation, backend working directory and bounded lifetime required')
    os.environ['TRANSCRIPT_PG_TEST']='1'
    try:asyncio.run(serve(args))
    except KeyboardInterrupt:pass
    except Exception:
        print('Live rehearsal startup failed; inspect synthetic fixture/configuration offline. No demo DB targeted.',file=sys.stderr)
        raise SystemExit(1) from None
