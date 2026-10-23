# Recruiter scheduling review

## Implemented

The recruiter selects an eligible saved evaluation for the active job in Interview
Scheduling, enters a local date/start time, IANA timezone and 15–180 minute
duration, and selects **Review interview**. The review shows the persisted Job
Reference, application/upload and batch references, confirmed criteria revision,
and human-readable start and end in the selected timezone. An eligible unscored
candidate requires its own uncertainty acknowledgement.

The recruiter checks the final confirmation and selects **Confirm booking**.
Review alone makes no booking request. Editing the inputs clears the review;
changing the selected job, candidate, batch or revision also clears it. The
confirmation handler revalidates the exact reviewed snapshot and future time.
Saved interviews show the Job Reference, start/end, timezone and candidate
reference and remain retrievable without an in-memory screening selection.

The existing authenticated booking service remains authoritative. It validates
job ownership, confirmed revision, saved batch/candidate association, completed
eligibility, explicit unscored selection, existing booking and recruiter overlap.
The frontend additionally checks batch membership and supported unscored reasons.
It never assumes a failed schedule-list request means no bookings. After an
unconfirmed write, another attempt requires reloading saved interviews; there is
no automatic write retry. A concurrent booking can still be rejected by the
server after review. This is a review step, not a slot reservation.

The controls reuse the shared card, field, button and confirmation styles, with
wrapping for long references. Browser viewport acceptance remains unverified.

## Email boundary and distinct scheduling paths

Recruiter-defined booking sends **no invitation or email**. Its existing interview
page manages the private joining invitation separately. Candidate self-scheduling
remains an explicitly labelled alternative in which the candidate chooses an
offered Asia/Dhaka slot. Bulk scheduling also sends slot-selection invitations;
it does not book the recruiter-reviewed appointment.

Inspection confirmed that `InterviewEmailAttempt` is linked by a non-null foreign
key to `SchedulingInvitation`, with a unique invitation/kind constraint. The
reviewed-send router creates a scheduling capability, and the candidate booking
path creates its joining capability and confirmation attempt. The existing
confirmation template formats Asia/Dhaka, while the self-scheduling booking path
fixes duration at 60 minutes. A
recruiter-booked joining-email action therefore needs a separate reviewed design
for recipient provenance, joining-token lifecycle, arbitrary timezone/duration,
durable reservation and uncertain-send recovery. No scheduling invitation is
fabricated just to reuse that attempt table. This remains **Planned**, not
implemented in this increment. SMTP acceptance must never be described as inbox
delivery. No actual email was sent during validation.

## Offline verification

- Frontend tests exercise the real booking handlers with mocked React hooks and
  API boundaries: review without writing, separate final acknowledgement, one
  booking request, edit invalidation, uncertain-write reconciliation, duplicate
  suppression and failed calendar loading. Pure and rendered tests cover wrong
  job/revision/application, excluded or failed evaluations, unscored approval,
  timezone preview and saved-summary reload.
- Existing backend tests use synthetic SQL doubles and fake mail transports for
  ownership, stale revisions, candidate/batch association, duplicates, overlap,
  timezone validation, invitation access and failed/uncertain email outcomes.
- No provider, SMTP, preserved database or browser/media connection is used.

Commands from the repository root (use the existing compatible Python environment):

```powershell
node --experimental-strip-types --test frontend/tests/*.test.ts
cd backend
python -m pytest tests/test_interviews.py tests/test_self_scheduling.py tests/test_interview_email.py tests/test_bulk_scheduling.py tests/test_interview_access.py -q -rs
```

Frontend TypeScript app/node checks and the Vite production build are also
required. The three bulk PostgreSQL concurrency cases require explicitly
authorized disposable infrastructure and were skipped; SQL-double tests do not
prove production transaction concurrency. No migration or backend behavior was
changed.

Results: 262 frontend tests passed (0 failed/skipped); 59 focused backend tests
passed (0 failed), with 3 disposable-PostgreSQL concurrency cases skipped. Both
TypeScript projects and the production build passed. The existing LiveKit chunk
size warning remains. No live browser or responsive viewport trial was performed.

## Recommended next increment

Design reviewed invitation delivery for an already booked interview using an
approved recipient and durable send reservation, including fail-closed handling
of uncertain delivery. Keep that separate from candidate slot selection. Before
deployment, perform a synthetic recruiter browser walkthrough at desktop and
mobile widths; do not send real email as part of that UI check.
