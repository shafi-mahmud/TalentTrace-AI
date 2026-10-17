"""Only synthetic artifacts; PG fixtures opt into the isolated test database."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select,delete,event,text
from app.core.config import settings
from app.db.models.reviewer_confirmation import ReviewerConfirmation as Record
from app.db.models.recruiter import CandidateScoreRecord as Score,JobProfile,InterviewSchedule as Interview
from app.db.models.interview_analysis import InterviewAnalysis as Analysis
from app.schemas.consolidated_assessment import ConsolidatedAssessment,InterviewEvidence
from app.schemas.reviewer_confirmation import ConfirmationInput
from app.services.reviewer_confirmation import validate_claims,sweep_confirmations,purge_interview_confirmations
from test_consolidated_assessment import artifacts,home_fixture,add_interview


def report():
    f=artifacts()
    return ConsolidatedAssessment(job_id=f.parent.job_id,job_title=f.snapshot['job_title'],job_reference=f.snapshot['job_reference'],
        batch_id=f.parent.batch_id,upload_id=f.parent.upload_id,criteria_revision=2,cv_source='current_saved_score',cv=f.score,
        confirmed_requirements=tuple(f.snapshot['criteria']),interview=InterviewEvidence(state='not_scheduled'))


def input_for(r,position='alignment',kind='cv',reason='supported_requirement',scope='cv_only'):
    ids=[c.criterion_id for c in r.confirmed_requirements]
    return ConfirmationInput(expected_version=0,evidence_token='a'*64,position=position,scope=scope,requirement_ids=ids,
        references=[dict(criterion_id=id,kind=kind,reason=reason) for id in ids])


@pytest.mark.parametrize('case',['positive','gap_only_negative','unsupported_positive','forged','missing_mandatory','no_context','extra_text','duplicate','fake_reviewer'])
def test_claim_gates_and_strict_contract(case):
    r=report();body=input_for(r)
    if case=='positive':validate_claims(r,body);return
    if case=='gap_only_negative':body=input_for(r,'mixed','gap','missing_evidence')
    if case=='unsupported_positive':r=r.model_copy(update={'cv':r.cv.model_copy(update={'score':None,'dimensions':(),'status':'not_evaluated','reason':'uncertain_evidence'})})
    if case=='forged':body=body.model_copy(update={'requirement_ids':['foreign']})
    if case=='missing_mandatory':
        from app.schemas.screening import ScreeningCriterion
        r=r.model_copy(update={'confirmed_requirements':r.confirmed_requirements+(ScreeningCriterion(criterion_id='mandatory',description='Mandatory example',category='skill',is_hard=True),)})
    if case=='no_context':r=r.model_copy(update={'confirmed_requirements':()})
    if case in {'extra_text','fake_reviewer','duplicate'}:
        payload=body.model_dump(mode='json')
        if case=='extra_text':payload['rationale']='Private source quotation'
        if case=='fake_reviewer':payload['reviewer_id']=str(uuid4())
        if case=='duplicate':payload['requirement_ids']*=2
        with pytest.raises(ValidationError):ConfirmationInput.model_validate(payload)
    else:
        from fastapi import HTTPException
        with pytest.raises(HTTPException):validate_claims(r,body)


async def get_body(f,position='alignment',scope='cv_only',reason='supported_requirement',kind='cv'):
    r=await f.client.get(f.path,headers=f.headers);assert r.status_code==200,r.text
    v=r.json();ids=[c['criterion_id'] for c in v['confirmed_requirements']]
    return dict(expected_version=v['confirmation']['version'],evidence_token=v['confirmation']['evidence_token'],
        position=position,scope=scope,requirement_ids=ids,references=[dict(criterion_id=id,kind=kind,reason=reason) for id in ids])


@pytest.mark.parametrize('case',['alignment','insufficient','unscored','unsupported','foreign','candidate','changed_criteria','rescore','historical','expiry','read_only','forged','replay','delete_source','replace_source'])
def test_pg_cv_confirmation(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            monkeypatch.setattr(settings,'reviewer_confirmation_enabled',True)
            if case=='historical':
                await add_interview(f)
                async with f.factory.begin() as db:(await db.get(JobProfile,f.parent.job_id)).revision=3
                assert (await f.client.get(f.path,headers=f.headers)).json()['confirmed_requirements']==[]
                return
            if case in {'unscored','unsupported'}:
                async with f.factory.begin() as db:
                    row=await db.scalar(select(Score).where(Score.job_id==f.parent.job_id));row.score=None
                    row.payload=f.score.model_copy(update={'score':None,'dimensions':(),'status':'not_evaluated','reason':'uncertain_evidence'}).model_dump(mode='json')
            body=await get_body(f,'insufficient' if case in {'insufficient','unscored'} else 'alignment',
                reason='missing_evidence' if case in {'insufficient','unscored'} else 'supported_requirement',kind='gap' if case in {'insufficient','unscored'} else 'cv')
            if case=='forged':body['references'][0]['criterion_id']='foreign'
            headers=f.foreign if case=='foreign' else {'cookie':'talenttrace_interview=synthetic'} if case=='candidate' else {**f.headers,'x-talenttrace-request':'1'}
            if case=='foreign':headers={**headers,'x-talenttrace-request':'1'}
            if case=='candidate':headers={**headers,'x-talenttrace-request':'1'}
            a=await f.client.put(f.path+'/confirmation',json=body,headers=headers)
            if case in {'foreign','candidate','unsupported','forged'}:
                assert a.status_code==({'foreign':404,'candidate':401}.get(case,422)),a.text;return
            assert a.status_code==200,a.text
            assert a.json()['state']=='confirmed' and a.json()['version']==1
            if case=='replay':assert (await f.client.put(f.path+'/confirmation',json=body,headers=headers)).status_code==409
            async with f.factory.begin() as db:
                row=await db.scalar(select(Record).where(Record.job_id==f.parent.job_id))
                assert row.reviewer_id==f.owner and row.expires_at<=row.confirmed_at+timedelta(days=30)
                assert 'ordered collection' not in str(row.source_versions) and not hasattr(row,'rationale')
                if case=='changed_criteria':(await db.get(JobProfile,f.parent.job_id)).revision+=1
                if case=='rescore':
                    score=await db.scalar(select(Score).where(Score.job_id==f.parent.job_id));score.score=None
                    score.payload=f.score.model_copy(update={'score':None,'dimensions':(),'status':'not_evaluated','reason':'uncertain_evidence'}).model_dump(mode='json')
                if case=='expiry':
                    row.confirmed_at=f.now-timedelta(days=31);row.expires_at=f.now-timedelta(days=1)
                if case in {'delete_source','replace_source'}:
                    await db.execute(delete(Score).where(Score.job_id==f.parent.job_id))
                    if case=='replace_source':db.add(Score(job_id=f.parent.job_id,batch_id=f.parent.batch_id,upload_id=f.parent.upload_id,
                        criteria_revision=2,scoring_version='f2-coverage-v1',score=f.score.score,payload=f.score.model_dump(mode='json')))
                    await db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
                    if case=='delete_source':
                        assert await db.scalar(select(Record).where(Record.job_id==f.parent.job_id)) is None;return
            if case=='changed_criteria':
                # Current F2 is absent at the new revision; no old judgment is exposed.
                assert (await f.client.get(f.path,headers=f.headers)).status_code==404;return
            statements=[]
            def sql(_c,_cur,statement,*a):statements.append(statement.strip().lower())
            event.listen(f.engine.sync_engine,'before_cursor_execute',sql)
            try:r=await f.client.get(f.path,headers=f.headers)
            finally:event.remove(f.engine.sync_engine,'before_cursor_execute',sql)
            assert r.status_code==200,r.text
            c=r.json()['confirmation'];assert c['state']==('restricted' if case=='expiry' else 'stale' if case=='rescore' else 'confirmed')
            if c['state']!='confirmed':assert c['position'] is None and c['references']==[] and c['reviewer_id'] is None
            assert not any(s.startswith(('insert ','update ','delete ')) for s in statements)
            if case=='expiry':
                async with f.factory.begin() as db:
                    assert await sweep_confirmations(db)==1
    asyncio.run(scenario())


async def coherent_interview(f):
    import copy
    from app.services.evaluation_input import build_input
    from app.services.interview_analysis import fingerprint
    from app.services.interview_qa import pair_transcript
    from app.services.interview_mapping import map_requirements
    f.snapshot['criteria'][0]['description']='Python'
    f.source=build_input(f.parent,f.snapshot,f.captures,f.turns)
    f.row.input_digest=fingerprint(f.source)
    f.row.result['requirements']=[m.model_dump(mode='json') for m in map_requirements(f.source,pair_transcript(f.source))]
    async with f.factory.begin() as db:
        (await db.get(JobProfile,f.parent.job_id)).confirmed_snapshot=copy.deepcopy(f.snapshot)
    await add_interview(f)


async def interview_body(f,position='mixed',reason='uncertain_finding',dimension='completeness'):
    body=await get_body(f,position,scope='cv_interview')
    for ref in body['references']:ref.update(kind='interview',reason=reason,qa_id=str(__import__('app.services.interview_qa',fromlist=['pair_transcript']).pair_transcript(f.source)[0].id),dimension=dimension)
    return body


@pytest.mark.parametrize('case',['mixed','ambiguous','withdrawn','deleted','expired','changed_source','changed_result','missing_analysis','cleanup','cleanup_failure','snapshot_rescore','stale_revision'])
def test_pg_interview_confirmation(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            monkeypatch.setattr(settings,'reviewer_confirmation_enabled',True)
            await coherent_interview(f)
            if case=='ambiguous':
                async with f.factory.begin() as db:
                    row=await db.get(Analysis,f.row.id)
                    db.add(Analysis(id=uuid4(),interview_id=row.interview_id,recruiter_id=row.recruiter_id,job_id=row.job_id,
                        input_digest=row.input_digest,criteria_revision=2,rubric_version=row.rubric_version,provider='mock',model='other',
                        corpus_version=row.corpus_version,status='completed',attempt=1,claim=uuid4(),lease_expires_at=row.lease_expires_at,
                        created_at=row.created_at,updated_at=row.updated_at,result=row.result))
            body=await interview_body(f)
            a=await f.client.put(f.path+'/confirmation',json=body,headers={**f.headers,'x-talenttrace-request':'1'})
            if case=='ambiguous':assert a.status_code==409,a.text;return
            assert a.status_code==200,a.text
            assert a.json()['scope']=='cv_interview'
            async with f.factory.begin() as db:
                i=await db.get(Interview,f.parent.id);row=await db.get(Analysis,f.row.id)
                if case in {'withdrawn','cleanup','cleanup_failure'}:i.transcript_storage_revoked_at=f.now
                if case=='deleted':i.transcript_deletion_status='deleted';i.transcript_deleted_at=f.now
                if case=='expired':i.transcript_retention_deadline=f.now-timedelta(seconds=1)
                if case=='changed_source':
                    from app.db.models.interview_transcript import InterviewTranscriptTurn as Turn
                    (await db.get(Turn,f.turns[1].id)).text='Changed synthetic answer.'
                if case=='changed_result':
                    import copy
                    value=copy.deepcopy(row.result);value['assessment']['answers'][0]['follow_up']='Changed synthetic follow-up.';row.result=value
                if case=='missing_analysis':await db.delete(row)
                if case=='snapshot_rescore':await db.execute(delete(Score).where(Score.job_id==f.parent.job_id))
                if case=='stale_revision':(await db.get(JobProfile,f.parent.job_id)).revision=3
            r=await f.client.get(f.path,headers=f.headers);assert r.status_code==200,r.text
            c=r.json()['confirmation']
            expected='confirmed' if case in {'mixed','snapshot_rescore'} else 'restricted' if case in {'withdrawn','deleted','expired','cleanup','cleanup_failure'} else 'stale'
            assert c['state']==expected,c
            if expected!='confirmed':assert c['position'] is None and c['references']==[]
            if case=='cleanup':
                async with f.factory.begin() as db:
                    await purge_interview_confirmations(db,f.parent.id)
                    assert await db.scalar(select(Record).where(Record.interview_id==f.parent.id)) is None
            if case=='cleanup_failure':
                from app.services import reviewer_confirmation as service
                from app.services.transcript_privacy import TranscriptPrivacyService
                from app.services.interview_transcripts import TranscriptPersistenceService,TranscriptError
                privacy=TranscriptPrivacyService(TranscriptPersistenceService(f.factory,None,clock=lambda:f.now))
                async def fail(*a,**k):raise RuntimeError('synthetic cleanup failure')
                monkeypatch.setattr(service,'purge_interview_confirmations',fail)
                # A failed deletion cannot remove the already committed revocation fence.
                with pytest.raises(TranscriptError):
                    await privacy.delete_revoked(f.owner,f.parent.id)
                assert (await f.client.get(f.path,headers=f.headers)).json()['confirmation']['state']=='restricted'
    asyncio.run(scenario())


@pytest.mark.parametrize('case',['updates','withdrawal_first','confirmation_first'])
def test_pg_concurrent_confirmation(monkeypatch,case):
    async def scenario():
        from test_comparison_snapshot import committed_fixture
        from app.services import reviewer_confirmation as service
        async with committed_fixture(monkeypatch) as (f,b,factory):
            monkeypatch.setattr(settings,'reviewer_confirmation_enabled',True)
            f.path=f'/api/v1/jobs/{f.parent.job_id}/batches/{f.parent.batch_id}/candidates/{f.parent.upload_id}/assessment'
            if case=='updates':
                body=await get_body(f)
                headers={**f.headers,'x-talenttrace-request':'1'}
                a,b=await asyncio.gather(f.client.put(f.path+'/confirmation',json=body,headers=headers),f.client.put(f.path+'/confirmation',json=body,headers=headers))
                assert sorted([a.status_code,b.status_code])==[200,409],(a.text,b.text)
                async with factory() as db:assert (await db.scalar(select(Record).where(Record.job_id==f.parent.job_id))).version==1
                return
            body=await get_body(f,scope='cv_interview')
            entered=asyncio.Event();release=asyncio.Event()
            if case=='withdrawal_first':
                async def writer():
                    async with factory.begin() as db:
                        i=await db.scalar(select(Interview).where(Interview.id==f.parent.id).with_for_update())
                        entered.set();await release.wait();i.transcript_storage_revoked_at=f.now
                task=asyncio.create_task(writer());await entered.wait()
                mutation=asyncio.create_task(f.client.put(f.path+'/confirmation',json=body,headers={**f.headers,'x-talenttrace-request':'1'}))
                release.set();await task
                r=await mutation;assert r.status_code==409,r.text
            else:
                original=service.sources
                async def held(*args,**kwargs):
                    result=await original(*args,**kwargs)
                    if len(args)>2 and args[2]=='cv_interview' and not entered.is_set():
                        entered.set();await release.wait()
                    return result
                monkeypatch.setattr(service,'sources',held)
                mutation=asyncio.create_task(f.client.put(f.path+'/confirmation',json=body,headers={**f.headers,'x-talenttrace-request':'1'}))
                await asyncio.wait_for(entered.wait(),10)
                async def writer():
                    async with factory.begin() as db:
                        i=await db.scalar(select(Interview).where(Interview.id==f.parent.id).with_for_update())
                        i.transcript_storage_revoked_at=f.now
                task=asyncio.create_task(writer());release.set()
                r=await mutation;assert r.status_code==200,r.text
                await task
                r=await f.client.get(f.path,headers=f.headers)
                assert r.json()['confirmation']['state']=='restricted' and r.json()['confirmation']['position'] is None
    asyncio.run(scenario())


@pytest.mark.parametrize('case',['supported','forged_question','unlinked_requirement','articulation_only','concern','excluded'])
def test_interview_positive_reference_gates(case):
    from app.services.evaluation_input import build_input
    from app.services.interview_analysis import fingerprint
    from app.services.interview_qa import pair_transcript
    from app.services.interview_mapping import map_requirements
    from app.services.consolidated_assessment import checked_result
    from fastapi import HTTPException
    f=artifacts();f.snapshot['criteria'][0]['description']='Python'
    f.source=build_input(f.parent,f.snapshot,f.captures,f.turns);f.row.input_digest=fingerprint(f.source)
    f.row.result['requirements']=[m.model_dump(mode='json') for m in map_requirements(f.source,pair_transcript(f.source))]
    for dimension in f.row.result['assessment']['answers'][0]['dimensions']:
        if dimension['dimension']=='completeness':dimension.update(status='supported',evidence=[{'turn_id':str(f.turns[1].id),'quote':'ordered collection'}])
        if case=='concern' and dimension['dimension']=='relevance':dimension['status']='concern'
    i=checked_result(f.row,f.source)
    r=report().model_copy(update={'cv':f.score,'confirmed_requirements':tuple(__import__('app.schemas.screening',fromlist=['ScreeningCriterion']).ScreeningCriterion.model_validate(c) for c in f.snapshot['criteria']),'interview':i})
    body=input_for(r,scope='cv_interview').model_dump(mode='json')
    body['references']=[{'criterion_id':r.confirmed_requirements[0].criterion_id,'kind':'interview','reason':'supported_requirement','qa_id':str(i.pairs[0].id),'dimension':'completeness'}]
    if case=='forged_question':body['references'][0]['qa_id']=str(uuid4())
    if case=='unlinked_requirement':body['references'][0]['criterion_id']='foreign'
    if case=='articulation_only':body['references'][0]['dimension']='articulation'
    if case=='excluded':r=r.model_copy(update={'cv':r.cv.model_copy(update={'screening_decision':'excluded'})})
    body=ConfirmationInput.model_validate(body)
    if case=='supported':validate_claims(r,body)
    else:
        with pytest.raises(HTTPException):validate_claims(r,body)


def test_pg_expiry_constraint(monkeypatch):
    async def scenario():
        from sqlalchemy.exc import IntegrityError
        async with home_fixture(monkeypatch) as f:
            monkeypatch.setattr(settings,'reviewer_confirmation_enabled',True)
            body=await get_body(f)
            assert (await f.client.put(f.path+'/confirmation',json=body,headers={**f.headers,'x-talenttrace-request':'1'})).status_code==200
            with pytest.raises(IntegrityError):
                async with f.factory.begin() as db:
                    row=await db.scalar(select(Record).where(Record.job_id==f.parent.job_id))
                    row.expires_at=row.confirmed_at+timedelta(days=31)
                    await db.flush()
    asyncio.run(scenario())
