"""Explicit developer rehearsal; disposable DB and fictional finalized input only.

Run from backend/. Never applies migrations to a configured application database.
No inference occurs until the disclosed recruiter UI/API action.
"""
import argparse
import asyncio
import os
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))


async def serve(configuration):
    from pydantic import SecretStr
    from dotenv import dotenv_values
    import uvicorn
    from test_interview_transcripts import pg,fixture
    from test_interview_analysis_api import seeded
    from app.core.config import settings
    from app.core.auth import hash_password,session_factory
    from app.db.models.recruiter import Recruiter
    from app.services.evaluation_input import PostInterviewInputService
    from app.services.interview_analysis import AnalysisManager
    from app.services.interview_mapping import SyntheticTechnicalRetriever
    from app.integrations.llm.interview_evaluation import GroqInterviewAssessment
    from app.agents.evaluation.workflow import InterviewEvaluationWorkflow
    from app.api.routers import interview_analysis
    from app.services.transcript_privacy import TranscriptPrivacyService
    from types import SimpleNamespace

    values=dotenv_values(configuration.env_file) if configuration.env_file else os.environ
    key,model=values.get('GROQ_API_KEY'),values.get('LLM_MODEL')
    if not key or not model:raise RuntimeError('Missing configured provider')
    generator=pg.__wrapped__();url=next(generator);f=None
    try:
        f=await fixture(url);await seeded(f)
        settings.database_url=SecretStr(url.render_as_string(hide_password=False))
        settings.environment='development'
        settings.cors_origins=['http://127.0.0.1:5190']
        settings.interview_email_enabled=False
        settings.livekit_synthetic_demo_enabled=False
        settings.transcript_storage_enabled=True
        settings.interview_evaluation_enabled=True
        settings.interview_evaluation_synthetic_job_ids=[f.job]
        settings.groq_api_key=SecretStr(key);settings.llm_model=model
        session_factory.cache_clear()
        password=secrets.token_urlsafe(24)
        async with f.factory.begin() as db:
            user=await db.get(Recruiter,f.owner);email=user.email
            user.password_hash=hash_password(password)
        private=ROOT/'data/milestone3';private.mkdir(parents=True,exist_ok=True)
        (private/'LOGIN.txt').write_text(email+'\n'+password+'\n')
        manager=AnalysisManager(PostInterviewInputService(f.service),
            InterviewEvaluationWorkflow(GroqInterviewAssessment(key,model),SyntheticTechnicalRetriever()),[f.job])
        interview_analysis.manager=lambda:manager
        from app.services import transcript_runtime
        transcript_runtime.runtime=lambda:SimpleNamespace(privacy=TranscriptPrivacyService(f.service))
        from app.main import app
        # The test helpers import app before configuration; keep exact dev CORS.
        from fastapi.middleware.cors import CORSMiddleware
        for middleware in app.user_middleware:
            if middleware.cls is CORSMiddleware:middleware.kwargs['allow_origins']=settings.cors_origins
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8022,log_level='critical',access_log=False))
        async def deadline():
            await asyncio.sleep(configuration.max_runtime_seconds);server.should_exit=True
        timer=asyncio.create_task(deadline())
        print('Disposable backend: http://127.0.0.1:8022. Login is in ignored data/milestone3/LOGIN.txt. No model request has run.',flush=True)
        print(f'Start the dedicated frontend on 5190. Ctrl+C stops this backend and removes its disposable database; maximum runtime {configuration.max_runtime_seconds} seconds.',flush=True)
        try:await server.serve()
        finally:
            timer.cancel();await manager.close()
    finally:
        if f:await f.engine.dispose()
        try:next(generator)
        except StopIteration:pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',help='Existing private file; reads only GROQ_API_KEY and LLM_MODEL')
    parser.add_argument('--confirm-free-tier-synthetic',action='store_true')
    parser.add_argument('--max-runtime-seconds',type=int,default=1800)
    args=parser.parse_args()
    if not args.confirm_free_tier_synthetic or Path.cwd()!=ROOT/'backend' or not 30<=args.max_runtime_seconds<=1800:
        parser.error('Run from backend/ with explicit free-tier synthetic confirmation.')
    os.environ['TRANSCRIPT_PG_TEST']='1'
    try:asyncio.run(serve(args))
    except KeyboardInterrupt:pass
    except Exception:
        print('Disposable rehearsal could not start or complete. No demo database is targeted.',file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':main()
