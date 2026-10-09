"""Owner-scoped PostgreSQL records around the existing conversational service."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.db.models.recruiter import ChatTurn, JobProfile, RecruiterConversation
from app.schemas.batch_screening import ReviewedJobSnapshot
from app.schemas.recruiter_chat import ExtractedJobRequirements, RecruiterChatRequest, RecruiterChatResponse
from app.services.recruiter_chat import ConversationStore, _Conversation, _GroundedItem


def private_settings(request: Request):
    return settings.model_copy(update={"cv_upload_root": settings.cv_upload_root / str(request.state.recruiter_id)})


async def owned_job(session, owner_id: UUID, job_id: UUID, *, lock=False):
    query = select(JobProfile).where(JobProfile.id == job_id, JobProfile.recruiter_id == owner_id)
    if lock:
        query = query.with_for_update()
    job = await session.scalar(query)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


async def owned_reference(session, owner_id: UUID, reference: str, *, lock=False):
    query = select(JobProfile).where(JobProfile.job_reference == reference, JobProfile.recruiter_id == owner_id)
    if lock:
        query = query.with_for_update()
    job = await session.scalar(query)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


def restore_conversation(row):
    state = row.state
    messages = [RecruiterChatRequest(message=message).message for message in state.get("messages", [])]
    if len(messages) > ConversationStore.MAX_TURNS or sum(map(len, messages)) > ConversationStore.MAX_CHARACTERS:
        raise ValueError("Invalid stored conversation bounds.")
    from app.services.recruiter_chat import LIST_FIELDS
    stored = {name: ([] if name in LIST_FIELDS else None) for name in ExtractedJobRequirements.model_fields}
    stored.update(state.get("requirements", {}))
    requirements = ExtractedJobRequirements.model_validate(stored)
    fields = requirements.model_dump(exclude_none=True)
    grounded = {name: [_GroundedItem(**item) for item in (items if isinstance(items, list) else [items])]
                for name, items in fields.items() if items}
    from app.schemas.recruiter_chat import FIELD_LABELS
    uncertain = set(state.get("uncertain_fields", []))
    asked = state.get("last_asked_field")
    if not uncertain.issubset(FIELD_LABELS) or (asked is not None and asked not in FIELD_LABELS):
        raise ValueError("Invalid stored fields.")
    return _Conversation(conversation_id=row.id, messages=messages, total_characters=sum(map(len, messages)),
        requirements=grounded, uncertain_fields=uncertain, last_asked_field=asked,
        last_generated_requirements=state.get("last_generated_requirements"))


def encode_conversation(item):
    return {"messages": list(item.messages), "requirements": {
        name: ([{"value": v.value, "evidence": v.evidence} for v in values] if name in
               {"responsibilities", "required_skills", "preferred_skills", "education_requirements"}
               else {"value": values[-1].value, "evidence": values[-1].evidence})
        for name, values in item.requirements.items() if values},
        "uncertain_fields": sorted(item.uncertain_fields), "last_asked_field": item.last_asked_field,
        "last_generated_requirements": item.last_generated_requirements}


async def persist_chat(session, owner_id, request, service, correlation_id):
    now = datetime.now(timezone.utc)
    if request.conversation_id:
        row = await session.scalar(select(RecruiterConversation).where(
            RecruiterConversation.id == request.conversation_id, RecruiterConversation.recruiter_id == owner_id).with_for_update())
        if row is None:
            raise HTTPException(404, "Conversation not found.")
        if row.expires_at <= now:
            from app.services.recruiter_chat import ConversationUnavailableError
            raise ConversationUnavailableError
    else:
        row = RecruiterConversation(id=uuid4(), recruiter_id=owner_id, expires_at=now+timedelta(minutes=30), state={})
        session.add(row)
        await session.flush()
    store = ConversationStore()
    current = restore_conversation(row)
    store._sessions[row.id] = current
    service._conversations = store
    response = await service.respond(request.model_copy(update={"conversation_id": row.id}), correlation_id=correlation_id)
    if response.status == "jd_generated":
        job = await session.scalar(select(JobProfile).where(JobProfile.conversation_id == row.id,
                                                           JobProfile.recruiter_id == owner_id))
        if job is None:
            job_id = uuid4()
            job = JobProfile(id=job_id, recruiter_id=owner_id, conversation_id=row.id,
                             job_reference="TT-JOB-"+job_id.hex[:16].upper(), revision=0)
            session.add(job)
        job.job_title = response.screening_suggestions.job_title
        job.draft = response.job_description_result.model_dump(mode="json")
        job.suggestions = response.screening_suggestions.model_dump(mode="json")
        job.sources = [item.model_dump(mode="json", exclude_none=True) for item in response.screening_suggestion_sources]
        job.confirmed_snapshot = None
        job.revision += 1
        response = response.model_copy(update={"draft_id": job.id, "job_reference": job.job_reference, "job_revision": job.revision})
    row.state = encode_conversation(current)
    row.expires_at = now + timedelta(minutes=30)
    # Every successful submission is persisted; errors roll back instead of asserting delivery.
    from sqlalchemy import func
    sequence = (await session.scalar(select(func.count()).select_from(ChatTurn).where(ChatTurn.conversation_id == row.id))) + 1
    session.add(ChatTurn(conversation_id=row.id, sequence=sequence, recruiter_message=request.message,
                         response=response.model_dump(mode="json", exclude_none=True)))
    await session.commit()
    return response


def job_view(job):
    try:
        return _validated_job_view(job)
    except (ValidationError, ValueError, TypeError, KeyError):
        raise HTTPException(500, "Saved job could not be validated.") from None


def _validated_job_view(job):
    # Validate stored artifacts before returning them to the client.
    from app.schemas.batch_screening import ScreeningSuggestions
    from app.schemas.job_description import JobDescriptionGenerationResponse
    from app.schemas.recruiter_chat import ScreeningSuggestionSource
    suggestions = ScreeningSuggestions.model_validate(job.suggestions)
    sources = [ScreeningSuggestionSource.model_validate(source) for source in job.sources]
    snapshot = ReviewedJobSnapshot.model_validate(job.confirmed_snapshot) if job.confirmed_snapshot else None
    if (suggestions.job_title != job.job_title or (snapshot and (
        snapshot.job_reference != job.job_reference or snapshot.job_title != job.job_title or
        snapshot.criteria != suggestions.criteria))):
        raise ValueError("Invalid stored job association.")
    return {"id": str(job.id), "job_reference": job.job_reference, "job_title": job.job_title,
            "revision": job.revision, "conversation_id": str(job.conversation_id) if job.conversation_id else None,
            "suggestions": suggestions.model_dump(mode="json"),
            "sources": [s.model_dump(mode="json", exclude_none=True) for s in sources],
            "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
            "draft": JobDescriptionGenerationResponse.model_validate(job.draft).model_dump(mode="json") if job.draft else None}
