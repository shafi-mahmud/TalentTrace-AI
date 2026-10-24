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

The manually entered recipient is checked against the administrator allowlist;
this does not independently establish that the address belongs to that candidate.
The recruiter must confirm the intended recipient using the application reference.
No recipient audit history is retained in this minimal journal.

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

## Verification (synthetic only)

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
