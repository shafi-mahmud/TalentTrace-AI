"""PostgreSQL identity/leases. Interview lock precedes every derived-row lock."""
import asyncio
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.interview_analysis import InterviewAnalysis as Record
from app.services.interview_analysis import AnalysisManager,Operation,fingerprint
from app.services.interview_transcripts import transaction,TranscriptError
from app.agents.evaluation.workflow import RUBRIC_VERSION,AssessmentError
from app.rag.technical_references import CORPUS_VERSION


class DurableAnalysisManager(AnalysisManager):
    def row_view(self,row):
        return {'operation_id':str(row.id),'status':row.status,'error':row.error,
            'attempt':row.attempt,'persistence':'postgresql_privacy_bound',
            'result':row.result if row.status=='completed' else None}

    def expire_claim(self,row,now):
        if row.status=='running' and now>=row.lease_expires_at:
            row.status='failed';row.result=None;row.error='evaluation_worker_interrupted';row.updated_at=now

    async def start(self,request,job,interview,revision,operation_id,retry_failed=False,expected_attempt=None):
        if job not in self.allowed_jobs:raise HTTPException(403,'Synthetic job is not approved.')
        launch=None
        async with transaction(self.inputs.storage.factory) as db:
            source=await self.inputs.load(db,request,job_id=job,interview_id=interview,revision=revision)
            digest=fingerprint(source);now=self.inputs.storage.clock();owner=request.state.recruiter_id
            existing=await db.get(Record,operation_id)
            if existing and (existing.interview_id,existing.job_id,existing.recruiter_id,existing.input_digest)!=(interview,job,owner,digest):
                raise HTTPException(409,'Operation identity conflicts with current input.')
            if existing and (existing.rubric_version,existing.model,existing.corpus_version)!=(RUBRIC_VERSION,self.workflow.provider.model,CORPUS_VERSION):
                raise HTTPException(409,'Operation identity has a different model, rubric or corpus version.')
            row=existing or await db.scalar(select(Record).where(Record.interview_id==interview,Record.input_digest==digest,
                Record.rubric_version==RUBRIC_VERSION,Record.model==self.workflow.provider.model,Record.corpus_version==CORPUS_VERSION).with_for_update())
            if row:
                self.expire_claim(row,now)
                if retry_failed:
                    if row.status!='failed' or type(expected_attempt) is not int or row.attempt!=expected_attempt:
                        raise HTTPException(409,'Retry requires the current failed attempt number.')
                else:return self.row_view(row)
            elif retry_failed:raise HTTPException(409,'No failed operation to retry.')
            active=await db.scalar(select(Record.id).where(Record.interview_id==interview,Record.status=='running',Record.lease_expires_at>now))
            if active:raise HTTPException(409,'An interview analysis is already active.')
            claim=uuid4()
            if row:
                row.attempt+=1;row.claim=claim;row.status='running';row.result=None;row.error=None
                row.lease_expires_at=now+timedelta(seconds=150);row.updated_at=now
            else:
                row=Record(id=operation_id,interview_id=interview,recruiter_id=owner,job_id=job,input_digest=digest,
                    criteria_revision=revision,rubric_version=RUBRIC_VERSION,provider=self.workflow.provider.name,
                    model=self.workflow.provider.model,corpus_version=CORPUS_VERSION,status='running',attempt=1,claim=claim,
                    lease_expires_at=now+timedelta(seconds=150),created_at=now,updated_at=now,error=None,result=None)
                db.add(row)
            launch=Operation(row.id,job,interview,digest,revision,owner)
            launch.claim,launch.attempt=claim,row.attempt
            view=self.row_view(row)
        # The claim transaction has committed; no transaction spans inference.
        self.operations[launch.id]=launch
        launch.task=asyncio.create_task(self.execute(launch,request,source))
        return view

    async def execute(self,item,request,source):
        await super().execute(item,request,source)
        try:
            async with transaction(self.inputs.storage.factory) as db:
                current=await self.inputs.load(db,request,job_id=item.job,interview_id=item.interview,revision=item.revision)
                if fingerprint(current)!=item.digest:raise AssessmentError('evaluation_source_changed')
                row=await db.scalar(select(Record).where(Record.id==item.id).with_for_update())
                if row is None or (row.claim,row.attempt)!=(item.claim,item.attempt):return
                now=self.inputs.storage.clock();self.expire_claim(row,now)
                if row.status!='running':return
                row.status='completed' if item.state=='completed' else 'failed'
                row.result=item.result if row.status=='completed' else None
                row.error=item.error;row.updated_at=now
        except Exception:
            # Fail closed. Never save text through a privacy/source failure.
            # A surviving claim expires; GET identifies interruption, never completion.
            pass
        finally:item.result=None

    async def get(self,request,job,interview,operation_id):
        if job not in self.allowed_jobs:raise HTTPException(403,'Synthetic job is not approved.')
        async with transaction(self.inputs.storage.factory) as db:
            # Resolve revision without locking child first; ownership is rechecked below.
            revision=await db.scalar(select(Record.criteria_revision).where(Record.id==operation_id,Record.job_id==job,Record.interview_id==interview))
            if revision is None:raise HTTPException(404,'Analysis not found.')
            source=await self.inputs.load(db,request,job_id=job,interview_id=interview,revision=revision)
            row=await db.scalar(select(Record).where(Record.id==operation_id).with_for_update())
            if row is None or row.recruiter_id!=request.state.recruiter_id:raise HTTPException(404,'Analysis not found.')
            if row.input_digest!=fingerprint(source):raise AssessmentError('evaluation_source_changed')
            self.expire_claim(row,self.inputs.storage.clock())
            return self.row_view(row)

    async def maintain(self):
        while True:
            await asyncio.sleep(5)
            for key,item in list(self.operations.items()):
                if item.task and item.task.done():self.operations.pop(key,None)

    async def close(self):
        # Cancellation is a failed attempt; lease fencing prevents delayed commits.
        await super().close()
