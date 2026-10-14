from types import SimpleNamespace as N
from uuid import uuid4
import asyncio
import pytest
from fastapi import HTTPException
from app.api.routers import jobs

def test_owned_saved_batch_discovery(monkeypatch):
 job=N(id=uuid4(),revision=2,confirmed_snapshot={'confirmed':True});batch=uuid4()
 async def owned(*args):return job
 async def load(s,j,b):assert b==batch;return 'validated_saved_score'
 class Session:
  async def scalars(self,*a):return N(all=lambda:[batch])
  async def refresh(self,j):pass
 monkeypatch.setattr(jobs,'owned_job',owned);monkeypatch.setattr(jobs,'load_scores',load)
 assert asyncio.run(jobs.saved_job_scores(job.id,N(id=uuid4()),Session()))==['validated_saved_score']
 job.confirmed_snapshot=None
 with pytest.raises(HTTPException):asyncio.run(jobs.saved_job_scores(job.id,N(id=uuid4()),Session()))

def test_foreign_and_empty(monkeypatch):
 async def owned(*a):raise HTTPException(404,'Job not found')
 monkeypatch.setattr(jobs,'owned_job',owned)
 with pytest.raises(HTTPException):asyncio.run(jobs.saved_job_scores(uuid4(),N(id=uuid4()),N()))

@pytest.mark.parametrize('case',['empty','limit','stale'])
def test_bounds_and_revision(monkeypatch,case):
 job=N(id=uuid4(),revision=2,confirmed_snapshot={'confirmed':True})
 async def owned(*a):return job
 async def load(*a):return 'validated'
 class Session:
  async def scalars(self,*a):return N(all=lambda:[] if case=='empty' else [uuid4() for _ in range(21 if case=='limit' else 1)])
  async def refresh(self,j):
   if case=='stale':j.revision=3
 monkeypatch.setattr(jobs,'owned_job',owned);monkeypatch.setattr(jobs,'load_scores',load)
 if case=='empty':assert asyncio.run(jobs.saved_job_scores(job.id,N(id=uuid4()),Session()))==[]
 else:
  with pytest.raises(HTTPException):asyncio.run(jobs.saved_job_scores(job.id,N(id=uuid4()),Session()))
