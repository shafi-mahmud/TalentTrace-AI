"""Bounded recruiter-approved cohorts; reuse individual delivery and no retries."""
import hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from uuid import UUID
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.recruiter import CandidateScoreRecord,InterviewSchedule,SchedulingInvitation,InterviewEmailAttempt
from app.db.models.external_cv import ExternalCvSubmissionRecord
from app.db.models.bulk_scheduling import BulkSchedulingOperation
from app.schemas.external_cv import ApplicationContact,SourceId,SubmissionId
from app.schemas.cv_upload import JobReference
from app.schemas.batch_screening import ReviewedJobSnapshot
from pydantic import TypeAdapter
from app.services.score_records import restore_candidate_score,SCORING_VERSION
from app.services.recruiter_records import owned_job
from app.services.interview_booking import lock_interviewer
from app.services.interview_email import recipient,ready
from app.api.routers.interview_email import EmailSelection,send_selected_email
MAX_COHORT=100
MAX_RECIPIENTS=10

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
def masked(value):return value[:1]+'***@'+value.rsplit('@',1)[1]

def contact_fact(row):
    return {name:getattr(row,name,None) for name in ('id','job_id','source_job_reference','source_id','external_submission_id','application_email','contact_status','contact_validation_version','email_provenance','email_collection_type','content_sha256','file_type','size_bytes')}

def calculate(job,scores,contacts,scheduled,invited,configuration):
    """Pure, deterministic classification; never returns raw emails to browsers."""
    try:
        reviewed=ReviewedJobSnapshot.model_validate(job.confirmed_snapshot)
        if reviewed.job_reference!=job.job_reference:raise ValueError()
    except Exception:raise HTTPException(409,'Current confirmed criteria could not be validated.') from None
    groups=defaultdict(list);mapping=defaultdict(list)
    for row in scores:groups[(row.batch_id,row.upload_id)].append(row)
    for row in contacts:mapping[(row.batch_id,row.upload_id)].append(row)
    pairs=set(groups)|set(mapping)
    if len(pairs)>MAX_COHORT:raise HTTPException(422,'Candidate cohort exceeds the bounded demo limit.')
    entries=[];internal={};facts=[];eligible=0;valid_contacts=0;original_addresses={}
    for pair in sorted(pairs,key=lambda p:(str(p[0]),str(p[1]))):
        rows=groups[pair];current=[r for r in rows if r.criteria_revision==job.revision and r.scoring_version==SCORING_VERSION]
        reason=None;address=None;eligible_candidate=False
        if len(current)!=1:reason='stale_criteria' if rows else 'incomplete_result'
        else:
            row=current[0]
            try:
                candidate=restore_candidate_score(row.payload)
                if row.job_id!=job.id or candidate.upload_id!=row.upload_id or candidate.job_reference!=job.job_reference or candidate.score!=row.score or candidate.weights.model_dump()!=job.scoring_weights:
                    raise ValueError('Association mismatch')
                if candidate.screening_decision!='eligible':reason='ineligible'
                elif candidate.status!='scored' or candidate.score is None:reason='not_scored'
                else:
                    expected={c.criterion_id:c.category for c in reviewed.criteria}
                    actual={m.criterion_id:d.category for d in candidate.dimensions for m in d.matches}
                    if expected!=actual:raise ValueError('Current criteria evidence mismatch')
                    eligible+=1;eligible_candidate=True
            except Exception:reason='invalid_result'
        linked=mapping[pair]
        if reason is None:
            if len(linked)!=1:reason='missing_or_ambiguous_contact'
            else:
                contact=linked[0]
                try:
                    if contact.job_id!=job.id or contact.status!='pending_review':raise ValueError()
                    TypeAdapter(SourceId).validate_python(contact.source_id)
                    TypeAdapter(SubmissionId).validate_python(contact.external_submission_id)
                    TypeAdapter(JobReference).validate_python(contact.source_job_reference)
                    checked=ApplicationContact(email=contact.application_email,status=contact.contact_status,provenance=contact.email_provenance,collection_type=contact.email_collection_type,validation_version=contact.contact_validation_version)
                    if checked.status!='available':raise ValueError()
                    address=checked.email;valid_contacts+=1;original_addresses[pair]=address
                    recipient(configuration,address)
                except HTTPException:reason='not_allowlisted'
                except Exception:reason='missing_or_ambiguous_contact'
        if eligible_candidate and pair in scheduled:reason='already_scheduled'
        elif eligible_candidate and pair in invited:reason='already_invited'
        entry={'batch_id':str(pair[0]),'upload_id':str(pair[1]),'recipient_mask':masked(address) if address else None,'reason':reason}
        entry['approval_signature']=digest({'scores':[r.payload for r in current],'contacts':[contact_fact(r) for r in linked]})
        entries.append(entry)
        if reason is None:internal[pair]=address
        facts.append({'pair':[str(p) for p in pair],'scores':[digest(r.payload) for r in rows],'contacts':[digest(contact_fact(r)) for r in linked],'reason':reason})
    duplicates=Counter(address.casefold() for address in original_addresses.values())
    for entry in entries:
        pair=(UUID(entry['batch_id']),UUID(entry['upload_id']))
        if pair in internal and duplicates[internal[pair].casefold()]>1:
            entry['reason']='duplicate_recipient';del internal[pair]
    exclusions=dict(Counter(e['reason'] for e in entries if e['reason']))
    data={'criteria_revision':job.revision,'eligible_scored':eligible,'validated_contacts':valid_contacts,'sendable':len(internal),'exclusions':exclusions,'candidates':entries,'can_send':bool(internal) and len(internal)<=MAX_RECIPIENTS and ready(configuration),'maximum_recipients':MAX_RECIPIENTS}
    fingerprint=digest({'job':str(job.id),'revision':job.revision,'snapshot':job.confirmed_snapshot,'weights':job.scoring_weights,'facts':facts,'entries':entries,'allowlist':sorted(x.casefold() for x in configuration.interview_email_recipients),'origin':configuration.interview_public_origin,'ready':ready(configuration)})
    return data,internal,fingerprint

async def cohort(session,owner,job_id,configuration):
    job=await owned_job(session,owner,job_id)
    await session.refresh(job)
    if job.confirmed_snapshot is None:raise HTTPException(409,'Confirm current job criteria first.')
    scores=(await session.scalars(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id==job_id).order_by(CandidateScoreRecord.id).limit(MAX_COHORT+1).execution_options(populate_existing=True))).all()
    contacts=(await session.scalars(select(ExternalCvSubmissionRecord).where(ExternalCvSubmissionRecord.job_id==job_id).order_by(ExternalCvSubmissionRecord.id).limit(MAX_COHORT+1).execution_options(populate_existing=True))).all()
    if len(scores)>MAX_COHORT or len(contacts)>MAX_COHORT:raise HTTPException(422,'Candidate cohort exceeds the bounded demo limit.')
    bookings=(await session.scalars(select(InterviewSchedule).where(InterviewSchedule.job_id==job_id).limit(MAX_COHORT+1))).all()
    invitations=(await session.scalars(select(SchedulingInvitation).where(SchedulingInvitation.job_id==job_id).limit(MAX_COHORT+1))).all()
    if len(bookings)>MAX_COHORT or len(invitations)>MAX_COHORT:raise HTTPException(422,'Scheduling history exceeds the bounded demo limit.')
    data,targets,fingerprint=calculate(job,scores,contacts,{(r.batch_id,r.upload_id) for r in bookings},{(r.batch_id,r.upload_id) for r in invitations},configuration)
    return job,data,targets,fingerprint

def reply(op):
    status=op.status
    if status=='running' and datetime.now(timezone.utc)-op.updated_at>timedelta(minutes=5):status='review_required'
    counts={name:sum(x['status']==name for x in op.outcomes) for name in ['accepted','failed','uncertain','skipped','pending']}
    return {'operation_id':str(op.id),'job_id':str(op.job_id),'status':status,'criteria_revision':op.criteria_revision,'expires_at':op.expires_at,'preview':op.preview,'counts':counts,'outcomes':[{k:v for k,v in x.items() if k!='attempt_id'} for x in op.outcomes]}

async def preview(session,owner,job_id,revision,configuration):
    job,data,targets,fingerprint=await cohort(session,owner,job_id,configuration)
    if revision!=str(job.revision):raise HTTPException(409,'Review current job revision.')
    op=BulkSchedulingOperation(recruiter_id=owner,job_id=job_id,criteria_revision=job.revision,fingerprint=fingerprint,expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),status='preview',preview=data,outcomes=[])
    session.add(op);await session.commit();return reply(op)

async def operation(session,owner,job_id,operation_id):
    await owned_job(session,owner,job_id)
    op=await session.scalar(select(BulkSchedulingOperation).where(BulkSchedulingOperation.id==operation_id,BulkSchedulingOperation.job_id==job_id,BulkSchedulingOperation.recruiter_id==owner).execution_options(populate_existing=True))
    if op is None:raise HTTPException(404,'Operation unavailable.')
    return op

async def send(session,owner,job_id,operation_id,revision,configuration,sender=send_selected_email):
    await lock_interviewer(session,owner)
    op=await operation(session,owner,job_id,operation_id)
    if op.status!='preview':return reply(op) # Durable same-operation replay never sends again.
    active=await session.scalar(select(BulkSchedulingOperation.id).where(BulkSchedulingOperation.job_id==job_id,BulkSchedulingOperation.recruiter_id==owner,BulkSchedulingOperation.status=='running').limit(1))
    if active:raise HTTPException(409,'Another bulk operation is active; check its status.')
    job,data,targets,fingerprint=await cohort(session,owner,job_id,configuration)
    if op.expires_at<=datetime.now(timezone.utc) or revision!=str(job.revision) or op.fingerprint!=fingerprint:
        raise HTTPException(409,'Preview changed or expired. Refresh and confirm again.')
    if not data['can_send']:raise HTTPException(409,'No approved bounded recipient cohort or email configuration unavailable.')
    op.status='running';op.updated_at=datetime.now(timezone.utc)
    op.outcomes=[{**e,'status':'pending'} for e in data['candidates'] if e['reason'] is None]
    await session.commit() # Reserve before SMTP; no long transaction spans delivery.
    for index,outcome in enumerate(list(op.outcomes)):
        pair=(UUID(outcome['batch_id']),UUID(outcome['upload_id']))
        try:
            await lock_interviewer(session,owner)
            current_job,fresh,new_targets,_=await cohort(session,owner,job_id,configuration)
            entry=next((e for e in fresh['candidates'] if e['batch_id']==outcome['batch_id'] and e['upload_id']==outcome['upload_id']),None)
            if current_job.revision!=op.criteria_revision or pair not in new_targets or new_targets[pair]!=targets[pair] or not entry or entry['approval_signature']!=outcome['approval_signature']:
                status='skipped'
            else:
                body=EmailSelection(batch_id=pair[0],upload_id=pair[1],criteria_revision=job.revision,selection_confirmed=True,recipient=targets[pair])
                def reserved(attempt):
                    op.outcomes=[{**x,'attempt_id':str(attempt.id)} if i==index else dict(x) for i,x in enumerate(op.outcomes)]
                delivered=await sender(job_id,body,SimpleNamespace(id=owner),session,configuration=configuration,on_reserved=reserved)
                status='skipped' if delivered.get('reused') else delivered['email_status']
                if status not in {'accepted','failed','uncertain','skipped'}:status='skipped'
        except HTTPException:
            await session.rollback();status='skipped'
        except Exception:
            await session.rollback();status='uncertain'
        # A connection failure here leaves durable running/attempt state for review.
        op=await operation(session,owner,job_id,operation_id)
        op.outcomes=[{**x,'status':status} if i==index else dict(x) for i,x in enumerate(op.outcomes)]
        op.updated_at=datetime.now(timezone.utc);await session.commit()
    op.status='partial' if any(x['status'] in {'failed','uncertain'} for x in op.outcomes) else 'completed'
    op.updated_at=datetime.now(timezone.utc);await session.commit();return reply(op)


async def status_reply(session,op):
    """Read-only recovery from durable attempt IDs; never resends or changes records."""
    result=reply(op)
    for item,stored in zip(result['outcomes'],op.outcomes):
        if stored.get('attempt_id') and item['status'] in {'pending','uncertain'}:
            attempt=await session.scalar(select(InterviewEmailAttempt).join(SchedulingInvitation).where(
                InterviewEmailAttempt.id==UUID(stored['attempt_id']),SchedulingInvitation.job_id==op.job_id,
                SchedulingInvitation.recruiter_id==op.recruiter_id,SchedulingInvitation.batch_id==UUID(item['batch_id']),
                SchedulingInvitation.upload_id==UUID(item['upload_id'])))
            if attempt and attempt.status in {'accepted','failed','uncertain'}:item['status']=attempt.status
            elif attempt and result['status']=='review_required':item['status']='uncertain'
    result['counts']={name:sum(x['status']==name for x in result['outcomes']) for name in ['accepted','failed','uncertain','skipped','pending']}
    return result
