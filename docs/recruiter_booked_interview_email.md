# Recruiter-booked appointment confirmation

Implemented on `feature/trainer-interview-email`, based on local develop
`1d91de8d8557a65572176ad60634cee2c60c1c68`.

## Implemented recruiter flow

1. Schedule and confirm an interview using the existing scheduling review.
2. Beside a saved interview, select **Review appointment email**. The authenticated
   server loads the exact owned interview and its current job approval/revision.
3. Enter an explicitly allowlisted recipient and select **Preview saved appointment**.
4. Review the server-rendered Job Reference, application reference, saved start/end,
   duration and IANA timezone. Independently confirm the recipient and details.
5. Select **Send appointment confirmation** once. Reload delivery status to inspect
   the durable result, including after navigating away or a lost response.

This is clearly labelled **appointment confirmation only**. It contains no joining
link, capability or claim that media access is ready. No LiveKit configuration,
probe or connection is required. Stored invitation bearers cannot be recovered from
hashes; this increment deliberately never issues, rotates, revokes or changes an
invitation. Recruiters must separately arrange usable joining access before the
interview. Candidate-selected self-scheduling keeps its existing email workflow;
these new endpoints reject those bookings.

## Server and privacy contract

Routes under `/api/v1/jobs/{job_id}/interviews/{interview_id}/appointment-email`:
- GET: sanitized recorded status (an interrupted `sending` maps to `uncertain`).
- POST `/preview`: allowlisted recipient validation and saved appointment preview;
  no persistent write or email delivery.
- POST: strict explicit confirmation and digest of the exact reviewed saved
  appointment and recipient. Changes require review again.

Every route verifies authenticated recruiter/job/interview ownership and current
approved criteria revision. Sending serializes on the existing recruiter lock,
then commits a primary-key-unique interview reservation before SMTP I/O. The
reservation survives cancellation, process interruption and lost delivery responses.
A second request returns the recorded result without sending. Database uniqueness
provides an additional backstop. No attempt spans a database transaction over SMTP.

Statuses: **Accepted by SMTP**, **Failed**, **Delivery uncertain**, **Not configured**.
SMTP acceptance is not inbox delivery. No automatic retry, including failed sends.
An unresolved reservation remains uncertain; reconciliation requires an operator,
not an automatic resend or reservation deletion. Failure to save the final outcome
also returns uncertain and leaves the reservation in place.

The new table stores only interview identity, fixed status and creation time.
No recipient, body, preview digest, CV data or plaintext bearer is persisted there.
Preview includes application references, not names or private CV evidence. Recipient
and message content exist only for the explicit review/delivery operation; they
are never logged by this implementation. Client errors use fixed safe text, and
unexpected response fields are rejected. No remote telemetry is introduced.

The manually entered recipient is checked against the administrator allowlist.
For an imported application, the server now also resolves the unique persisted
batch/upload pair, verifies its job association and existing `ApplicationContact`
provenance contract, and requires the address to match that recorded contact.
It never searches by name, CV text or address, and rejects browser provenance.
A bridge source Job Reference may differ legitimately from the target F4 reference;
`job_id`, batch and upload provide the target association. Source changes are bound
into the preview digest and rechecked under the existing owned-job lock before
reservation. Missing/invalid imported contact fails closed, requiring trusted
operator correction; no alternate-recipient override is implemented.

The UI uses the existing bulk-scheduling masked-address convention and explicitly
states that Google Forms RESPONDER_INPUT is not verified mailbox ownership. Native
uploads without a ledger contact remain manually addressed and receive a clear
warning to independently verify the intended recipient. No address is autofilled
or automatically sent. No recipient audit history is retained in this minimal journal.

## Configuration and migration

The existing SMTP_SSL transport, credentials, sender, recipient allowlist and
`interview_email_enabled` switch are reused. This path remains development-only,
disabled by default. It does not relax existing joining-link URL or LiveKit checks.
Unlike the self-scheduling joining email, an appointment-only message requires no
public origin or media configuration. Production delivery remains unsupported by
the existing development-only email policy.

New linear head: `0017_booked_interview_email`, after
`0016_submission_deletion` (after `0015_reviewer_confirmation`). Its table is
`booked_interview_email_attempts`, keyed directly to `interview_schedules`, not
`scheduling_invitations`. Downgrade refuses to discard any reservations, preventing
accidental loss of the resend fence. Deployment needs a separately authorized
schema upgrade; no existing database was migrated. Readiness rejects schemas still
at 0016 or 0015. The isolated F3-F6 test runner's reviewed-head guard and existing
head assertions now recognize 0017; production Compose defaults are unchanged.

## Verification of the original Sprint 4 checkpoint (synthetic only)

- Full frontend Node suite: **294 passed, 0 failed, 0 skipped**.
- Selected backend regression suites: **109 passed, 0 failed, 3 skipped**.
  Includes new API/transport tests, existing scheduling/access/self-scheduling email,
  bulk scheduling, N19 compatibility, notification contracts and Docker guards.
  Three skipped cases require the separate bulk-scheduling PostgreSQL opt-in.
- New disposable PostgreSQL acceptance: **1 passed**. Fresh random test-owned
  container, local image only, fresh volume, no host mounts, loopback ephemeral
  port, generated in-memory credentials. Migrated that new database through 0017.
  Confirmed reservation visible before SMTP, concurrent send refusal, exactly one
  fake delivery, interruption persistence and original invitation preservation.
  Only that new test container was stopped after verification.
- Readiness: **7 passed**, including rejection of 0016 and 0015.
- Transcript migration-chain regression: **1 passed**.
- Existing real PostgreSQL notification regression: **1 skipped**, separate explicit
  opt-in was not enabled. This is not a new notification acceptance claim.
- Total distinct selected backend/readiness cases: **118 passed, 4 skipped**;
  repeated focused runs are not counted twice.
- Frontend app/node TypeScript checks and production build passed.
- Git whitespace checks passed.

No real SMTP, provider call, email, media Join or protected database write occurred.
No browser visual acceptance was performed in this increment. Existing invitation
security and self-scheduling regressions passed; actual inbox delivery, joining-link
email capability and deployed browser acceptance remain unverified/unsupported.
The Docker F3-F6 container acceptance suite was not rerun; its offline guards passed.

Recommended next acceptance: review the appointment-only wording in a synthetic
browser walkthrough, then separately authorize deployment/migration/configuration
and any actual delivery. Joining-access email requires a separately reviewed bearer
lifecycle design; do not turn appointment confirmation into an unusable invitation.


## Review and authenticated acceptance — 24 October 2026

Confirmed defect in `d1a8a32`: an address could be allowlisted but belong to a
different imported application. That commit checked appointment ownership but did
not compare its entered recipient with the selected application's recorded contact.
This review fixes that mismatch and stale contact/source preview handling using
`ApplicationContact`, `SourceId`, `SubmissionId`, and the existing bulk-scheduling
`contact_fact`, `digest`, and `masked` helpers. Candidate self-scheduling semantics,
SMTP transport, invitation state and migration 0017 are unchanged.

Implemented association path: authenticated recruiter -> owned job -> exact saved
interview -> saved batch/upload -> unique trusted intake record belonging to that
job. Client-supplied name, CV text and provenance have no role in this path.

Authenticated ASGI API acceptance ran against a NEW disposable PostgreSQL database
migrated to 0017, using real auth cookies, ownership queries, preview/send routes,
reservation commits and status retrieval; only SMTP transport was faked. It covered
foreign recruiter/job rejection, unapproved and mismatched approved addresses,
changed saved schedule, changed persisted source identity, concurrent and duplicate
confirmation, accepted/failed/uncertain outcomes, reload and invitation preservation.
The separate PostgreSQL interruption test retained its no-resend reservation check.

A real browser then used the production frontend build connected directly to the
real FastAPI app and a second NEW disposable PostgreSQL database. It used normal
login and Home -> saved job -> Interview Scheduling -> saved appointment email.
The wrong allowlisted contact was blocked. The correct contact produced a masked
preview and unverified-mailbox warning. Explicit confirmation invoked fake SMTP
exactly once. Reloading the whole page and checking delivery status returned
Accepted by SMTP; SQL independently confirmed one accepted reservation. This proves
backend-connected browser behavior, not SMTP delivery or Google mailbox ownership.
The synthetic saved interview/contact were seeded test records; no Google API,
CV-import network call, LiveKit connection or real email was involved.

Sanitized screenshot and fixed-category count/status JSON are retained locally in
ignored `data/validation/`; neither artifact nor test credentials are committed.
The created browser tab, temporary server and new test-owned database were stopped.
All preserved services, worktrees, records and private evidence were left alone.

Review result: **PASS for synthetic appointment confirmation**.

- Final selected backend suites: **92 passed, 4 skipped, 0 failed**, including two
  actual PostgreSQL acceptance tests. Suites: `test_booked_email_postgres`,
  `test_booked_interview_email`, `test_interview_email`, `test_bulk_scheduling`,
  `test_application_bridge`, `test_interviews`, `test_interview_access`, and
  `test_self_scheduling`. Three bulk PostgreSQL cases and one bridge PostgreSQL
  case stayed skipped because their separate opt-ins were not enabled.
- Full frontend Node suite: **295 passed, 0 failed, 0 skipped**.
- Both TypeScript projects and production build passed. The existing large LiveKit
  bundle warning remains; this task did not change it.
- Git whitespace checks passed. Prior intermediate runs are not counted twice.

Remaining limitations: recorded contact association is validated, but Google Forms
respondent input is not independently verified mailbox ownership. Native uploads
have no guaranteed recorded contact and require manual recipient verification.
Missing/invalid imported contacts cannot use a manual override. No real SMTP,
inbox delivery, joining-access delivery or provider behavior was tested. Deployment
still requires review and a separately authorized 0017 schema upgrade on the target
environment; no preserved database has been migrated. This is ready for integration
review within that appointment-only scope, with no merge or push performed.
