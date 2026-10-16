"""Bounded single-worker ephemeral analysis. No durable transcript-derived store."""
import asyncio
import hashlib
import time
import re
from dataclasses import dataclass, field
from uuid import UUID
from fastapi import HTTPException
from app.agents.evaluation.workflow import AssessmentError,RUBRIC_VERSION
from app.services.evaluation_input import EvaluationInputError
from app.services.interview_transcripts import TranscriptError,transaction

DISCLOSURE_VERSION='synthetic-interview-analysis-v1'
DISCLOSURE='Synthetic development only: finalized dialogue and job criteria are sent to the configured Groq model. AI interpretations are advisory, unverified and require recruiter review. No hiring decision or numeric score is produced.'


def fingerprint(source):return hashlib.sha256(source.model_dump_json().encode()).hexdigest()


@dataclass(repr=False)
class Operation:
    id:UUID
    job:UUID
    interview:UUID
    digest:str
    revision:int
    owner:UUID
    created:float=field(default_factory=time.monotonic)
    state:str='running'
    error:str|None=None
    result:dict|None=None
    task:asyncio.Task|None=None


class AnalysisManager:
    def __init__(self,inputs,workflow,allowed_jobs):
        self.inputs,self.workflow,self.allowed_jobs=inputs,workflow,set(allowed_jobs)
        self.operations={};self.lock=asyncio.Lock()

    async def checked(self,request,job,interview,revision):
        if job not in self.allowed_jobs:raise HTTPException(403,'Synthetic evaluation is not approved for this job.')
        return await self.inputs.prepare(request,job_id=job,interview_id=interview,revision=revision)

    async def start(self,request,job,interview,revision,operation_id):
        source=await self.checked(request,job,interview,revision)
        digest=fingerprint(source);owner=request.state.recruiter_id
        async with self.lock:
            old=self.operations.get(operation_id)
            if old:
                if (old.job,old.interview,old.digest,old.owner)!=(job,interview,digest,owner):
                    raise HTTPException(409,'Operation identity conflicts with current input.')
                return self.view(old)
            for item in self.operations.values():
                if (item.job,item.interview,item.owner,item.digest)==(job,interview,owner,digest) and item.state in {'running','completed'}:
                    return self.view(item)
            if len(self.operations)>=20:raise HTTPException(409,'Analysis capacity unavailable; wait for expiry.')
            if sum(item.state=='running' for item in self.operations.values())>=1:
                raise HTTPException(409,'Another analysis is active in this development worker.')
            item=Operation(operation_id,job,interview,digest,revision,owner)
            self.operations[item.id]=item
            item.task=asyncio.create_task(self.execute(item,request,source))
            return self.view(item)

    async def execute(self,item,request,source):
        try:
            async with asyncio.timeout(110):
                # Recheck immediately before any provider work and after inference.
                fresh=await self.checked(request,item.job,item.interview,item.revision)
                if fingerprint(fresh)!=item.digest:raise AssessmentError('evaluation_source_changed')
                state=await self.workflow.run(source)
                fresh=await self.checked(request,item.job,item.interview,item.revision)
                if fingerprint(fresh)!=item.digest:raise AssessmentError('evaluation_source_changed')
                referenced={ref for pair in state['pairs'] for ref in pair.question_turns+pair.answer_turns}
                item.result={'provider':self.workflow.provider.name,'model':self.workflow.provider.model,
                    'outcome':'needs_review' if any(p.status=='uncertain' for p in state['pairs']) else 'assessed',
                    'inference_performed':state.get('inference_performed',True),
                    'rubric_version':RUBRIC_VERSION,'advisory':True,'scope':source.scope,'asr_review':source.asr_review,
                    'warning':source.warning,'criteria_revision':source.criteria_revision,
                    'pairs':[p.model_dump(mode='json') for p in state['pairs']],
                    'requirements':[m.model_dump(mode='json') for m in state['mappings']],
                    'technical_references':[r.model_dump(mode='json') for r in state['references']],
                    'assessment':state['assessment'].model_dump(mode='json'),
                    'turns':[t.model_dump(mode='json') for t in source.turns],
                    'unpaired_turn_ids':[str(t.id) for t in source.turns if t.id not in referenced],
                    'strengths':[{'qa_id':str(a.qa_id),'dimension':d.dimension,'interpretation':d.justification,
                        'evidence':[q.model_dump(mode='json') for q in d.evidence]} for a in state['assessment'].answers
                        for d in a.dimensions if d.status=='supported'],
                    'gaps':[{'criterion_id':m.criterion_id,'coverage':m.coverage,'follow_up':m.follow_up} for m in state['mappings']]}
                item.state='completed'
        except asyncio.CancelledError:
            item.result=None;item.state='unavailable';item.error='evaluation_interrupted'
        except (AssessmentError,EvaluationInputError,TranscriptError) as error:
            code=getattr(error,'code',str(error))
            item.result=None;item.state='failed'
            item.error=code if re.fullmatch(r'[a-z_]{1,100}',code) else 'evaluation_failed_or_source_unavailable'
        except (HTTPException,TimeoutError):
            item.result=None;item.state='failed';item.error='evaluation_failed_or_source_unavailable'
        except Exception:
            item.result=None;item.state='failed';item.error='evaluation_processing_failed'

    async def get(self,request,job,interview,operation_id):
        item=self.operations.get(operation_id)
        if item is None or item.job!=job or item.interview!=interview:raise HTTPException(404,'Analysis not found or lost after restart.')
        try:
            source=await self.checked(request,job,interview,item.revision)
            if fingerprint(source)!=item.digest:raise AssessmentError('evaluation_source_changed')
        except Exception:
            # Foreign callers cannot destroy another recruiter's result.
            if getattr(request.state,'recruiter_id',None)==item.owner:
                item.result=None;item.state='unavailable'
                if item.task and not item.task.done():item.task.cancel()
            raise
        if request.state.recruiter_id!=item.owner:raise HTTPException(404,'Analysis not found.')
        return self.view(item)

    def view(self,item):
        return {'operation_id':str(item.id),'status':item.state,'error':item.error,
            'persistence':'ephemeral_single_worker','result':item.result if item.state=='completed' else None}

    async def maintain(self):
        while True:
            await asyncio.sleep(5)
            for key,item in list(self.operations.items()):
                remove=time.monotonic()-item.created>=600
                try:
                    async with transaction(self.inputs.storage.factory) as db:
                        await self.inputs.storage._owned(db,item.owner,item.interview)
                except Exception:remove=True
                if remove:
                    item.result=None
                    if item.task and not item.task.done():item.task.cancel()
                    self.operations.pop(key,None)

    async def close(self):
        tasks=[i.task for i in self.operations.values() if i.task and not i.task.done()]
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        self.operations.clear()
