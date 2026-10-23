"""Bounded local discovery; no Google, CV parsing, scoring or candidate contact reads."""
from itertools import islice
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.db.models.application_view import ApplicationView
from app.db.models.external_cv import ExternalCvSubmissionRecord as Submission
from app.services.cv_extraction import CvExtractionService, CvExtractionError
from app.services.cv_upload import validate_document, CvUploadError

MAX_APPLICATIONS = 1000


def stored_applications(root: Path, reference: str):
    if root.is_symlink() or root.is_junction() or (root.exists() and not root.is_dir()):
        raise HTTPException(409, "Application storage requires review.")
    service = CvExtractionService(root)
    directory = service.root / reference
    if directory.is_symlink() or directory.is_junction() or (directory.exists() and not directory.is_dir()):
        raise HTTPException(409, "Application storage requires review.")
    if not directory.exists(): return {}, 0
    entries = list(islice(directory.iterdir(), MAX_APPLICATIONS + 1))
    if len(entries) > MAX_APPLICATIONS:
        raise HTTPException(409, "Application listing limit exceeded.")
    found, invalid = {}, 0
    for batch in entries:
        try:
            batch_id = UUID(batch.name)
            if str(batch_id) != batch.name: raise ValueError
            files = service.batch_files(reference, batch_id)
            # Metadata/signature validation only. No text extraction or model calls.
            for path in files: validate_document(path, path.suffix[1:])
        except (ValueError, CvExtractionError, CvUploadError, OSError):
            invalid += 1
            continue
        for path in files:
            found[(batch_id, UUID(path.stem))] = (path.suffix[1:], path.stat().st_size)
        if len(found) > MAX_APPLICATIONS:
            raise HTTPException(409, "Application listing limit exceeded.")
    return found, invalid


def reconcile(stored, ledger, viewed):
    # A bridged file appears in both stores. Stable identity is counted once.
    rows = {key: {"batch_id": key[0], "upload_id": key[1], "origin": "native_storage", "available": True}
            for key in stored}
    for row in ledger:
        key = (row.batch_id, row.upload_id)
        rows[key] = {"batch_id": key[0], "upload_id": key[1], "origin": "trusted_import",
                     "available": stored.get(key) == (row.file_type, row.size_bytes)}
    if len(rows) > MAX_APPLICATIONS:
        raise HTTPException(409, "Application listing limit exceeded.")
    items = [dict(rows[key], is_new=key not in viewed) for key in sorted(rows)]
    return items


async def discover(session, job, root):
    # Project only non-personal columns; no emails/submission IDs in this API.
    ledger = (await session.execute(select(Submission.batch_id, Submission.upload_id,
        Submission.file_type, Submission.size_bytes).where(Submission.job_id == job.id)
        .limit(MAX_APPLICATIONS + 1))).all()
    if len(ledger) > MAX_APPLICATIONS:
        raise HTTPException(409, "Application listing limit exceeded.")
    stored, invalid = await run_in_threadpool(stored_applications, root, job.job_reference)
    keys = [(row["batch_id"], row["upload_id"]) for row in reconcile(stored, ledger, set())]
    viewed = set((await session.execute(select(ApplicationView.batch_id, ApplicationView.upload_id)
        .where(ApplicationView.job_id == job.id,
               tuple_(ApplicationView.batch_id, ApplicationView.upload_id).in_(keys)))).all()) if keys else set()
    items = reconcile(stored, ledger, viewed)
    return {"job_id": job.id, "received_count": len(items),
            "new_count": sum(item["is_new"] for item in items),
            "unavailable_count": sum(not item["available"] for item in items),
            "invalid_batch_count": invalid, "applications": items}


async def mark_viewed(session, job, root, identities):
    snapshot = await discover(session, job, root)
    allowed = {(row["batch_id"], row["upload_id"]) for row in snapshot["applications"]}
    requested = {(row.batch_id, row.upload_id) for row in identities}
    if not requested <= allowed:
        raise HTTPException(409, "Application list changed. Refresh before marking viewed.")
    if requested:
        await session.execute(insert(ApplicationView).values([
            dict(job_id=job.id, batch_id=batch, upload_id=upload) for batch, upload in requested]
        ).on_conflict_do_nothing())
        await session.commit()
