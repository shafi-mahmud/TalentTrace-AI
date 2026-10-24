# Trainer Sprint 4 local integration — 24 October 2026

Base: local develop `1d91de8d8557a65572176ad60634cee2c60c1c68`.
Source: `feature/trainer-interview-email` at
`ac830fff7d983ec28d00cc2ac617c04f855e63e3`.

Both source and develop worktrees were clean. Source is a direct descendant of the
base and contains exactly the reviewed incremental commits:
- `d1a8a32` — reviewed appointment confirmation and durable reservation.
- `ac830ff` — imported contact association and acceptance fix.

An isolated `feature/trainer-sprint4-integration` branch/worktree was created from
develop and fast-forwarded to the source. No cherry-pick, squash, conflict or
production-code change was required. The integration adds only the connected
acceptance test and this evidence note. Source feature worktrees stay unchanged.

## Implemented workflow verified

The new `test_trainer_sprint4_integration.py` uses a newly created disposable
PostgreSQL container and real authenticated application routes/services:
1. Recruiter login and creation/listing of saved Job A and Job B.
2. Explicit review/confirmation of Job A criteria and approved scoring weights.
3. Deterministic screening over synthetic qualifications using the existing fake
   matcher, followed by real scoring arithmetic, score persistence and retrieval.
4. Exact trusted contact/metadata fixture for the same job/batch/upload, with a
   synthetic local document. Application counts deduplicate native storage/import
   ledger, mark only the displayed application viewed, and stay isolated by job.
5. Explicit candidate selection through the actual interview-booking endpoint.
   An unconfirmed request and foreign recruiter are rejected. A duplicate booking
   is rejected; the saved interview retains the exact owner/job/batch/upload.
6. Contact-checked email preview. A mismatched allowlisted address is rejected.
   The preview uses the saved job/application/appointment and provides no joining
   link or claim of media access.
7. Explicit send, one fake SMTP invocation, duplicate confirmation suppression,
   and recorded accepted status after a fresh authenticated client reloads it.
8. Application counts/viewed state and saved interview remain intact after email.
   No candidate invitation is created as a side effect.

This proves integration, not live model quality, Google intake or inbox delivery.
The screening input, trusted intake row and document are synthetic test fixtures;
no external source is contacted. Only the matcher and SMTP boundary are replaced;
booking, auth, authorization, SQL persistence, scoring, notifications and email
routes execute the real application implementation.

## Migration and deployment boundary

One Alembic head: `0017_booked_interview_email`, directly after
`0016_submission_deletion`. Fresh test-owned databases were migrated through it.
Readiness rejects existing schemas at 0016/0015, and no upgrade runs automatically.
No preserved database, active service, Docker lab or private configuration changed.
New test-owned containers were stopped by their fixture cleanup procedures.

## Limitations

Appointment confirmation remains separate from joining-access delivery. Matching
an imported record does not verify mailbox ownership (Google Forms RESPONDER_INPUT).
Native uploads without recorded contact still require independent manual recipient
verification. SMTP acceptance is not proof of inbox delivery; uncertain sends are
not retried. Deployment/migration and actual SMTP acceptance need separate approval.
No new browser trial was required here: the source checkpoint's backend-connected
browser evidence is historical; this integration reran full frontend tests and
connected backend acceptance, without claiming a new visual-browser pass.


## Final validation result: PASS

- Focused/backend integration and regression selection: **169 passed, 1 skipped,
  0 failed**. Includes the new complete pipeline, existing PostgreSQL concurrent
  and interrupted-send acceptance, email/access/scheduling, JD refinement, recruiter
  records, counts/notifications, scoring/ranking, Docker guards and N19 compatibility.
- Separate readiness suite: **7 passed, 0 failed**.
- Full frontend Node suite: **295 passed, 0 failed, 0 skipped**, including existing
  review/confirmation handlers, Home/JD/navigation, notifications and job isolation.
- Both TypeScript projects and production build passed. Existing large LiveKit
  bundle warning remains. Git whitespace checks passed.
- The skipped existing notification PostgreSQL test needs its independent opt-in.
  The new connected test verified real PostgreSQL notification/count/viewed-state
  behavior without enabling that separate fixture.

Counts are distinct cases; repeated/intermediate runs are not added together. No
production integration defect was demonstrated. The two source commits remain
intact, followed by this test/documentation commit. After successful checks, local
develop is authorized to fast-forward only to that verified integration commit.
No remote push is authorized or performed.
