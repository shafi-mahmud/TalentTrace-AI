# Candidate self-scheduling acceptance — 27 October 2026

Implementation baseline: `4bf9972932c62a2ffaa345e70572b4600b7e7a76`, branch
`feature/office-20261026-acceptance`. This acceptance reused the existing candidate
self-scheduling, invitation, booking and SMTP contracts. It did not implement a
second scheduler or change recruiter-defined appointment confirmation.

## Verdict

**PASS for bounded synthetic slot selection, durable booking and fake-SMTP
delivery-state acceptance. PARTIAL for candidate-facing refresh continuity.**
The booked interview persists in PostgreSQL and is visible to the owning recruiter
after browser refresh. The candidate page deliberately removes the scheduling
bearer from the address and retains it only in memory. Refresh loses that page's
confirmation/joining link; reopening the original consumed invitation refuses a
second booking rather than retrieving the confirmation. Save the private joining
link/email before leaving. No new candidate booking-retrieval capability was added.

Real SMTP delivery, mailbox ownership and functioning LiveKit media were **not**
tested. SMTP acceptance is not proof of inbox delivery. No external provider was
contacted and no media token or room was requested.

## Environment and boundaries

- New uniquely named test-owned Docker containers, internal PostgreSQL network and
  named volume; no host database port or preserved database reused. Only this new
  database was explicitly migrated to `0017_booked_interview_email`.
- Reused the installed backend test image and frontend dependencies; current
  backend source/tests were mounted read-only. No image/dependency download.
- Browser-only ingress exposed the test API on loopback. The application process
  blocked outbound socket connections except to its exact test database endpoint.
- Generated fictional recruiters/jobs and deterministic saved eligible F2 fixtures.
  This verifies scheduling from saved eligibility, not new CV/model inference.
- Real app authentication, authorization, HTTP handlers, booking locks, PostgreSQL
  persistence, React pages and Vite proxy. SMTP alone was replaced by a fake that
  retained synthetic messages privately. No frontend API responses were mocked.
- Joining configuration used local-only synthetic placeholders, with no LiveKit
  server. The fake messages used a synthetic HTTPS public origin. Only link
  structure/hash association and configuration validation were verified; actual
  public-origin reachability, invitation exchange and media were not exercised.
- The working Groq application, configuration, data and other runtimes were preserved.

## Actual browser workflow

1. Edge: signed in to a new synthetic recruiter account; selected its saved job,
   loaded saved scores and selected the eligible application.
2. Generated a private scheduling invitation. Explicitly entered the approved
   synthetic recipient and clicked **Send Scheduling Invitation**. The fake
   transport accepted it; UI distinguished acceptance from delivery. Sending
   replaced/revoked the earlier manually generated scheduling capability.
3. Chrome: opened the fake message's private scheduling capability without signing
   into a recruiter account. The fragment was removed immediately. Loaded actual
   current Asia/Dhaka office slots through the bearer-protected API.
4. Selected 28 October 2026, 08:00 Asia/Dhaka, and clicked **Book this interview**
   once. The real UI confirmed 60 minutes and confirmation-email acceptance.
5. Refreshed both pages. Candidate page correctly had no retained bearer or repeat
   booking action; its confirmation continuity limitation is recorded above.
   Recruiter reloaded saved interviews and saw 08:00–09:00, the correct job,
   application and criteria revision 2.
6. Eight independent API/database checks passed: exact saved booking; consumed
   scheduling capability; exact unclaimed joining-token association; two durable
   accepted fake email attempts; previous capability revoked; fresh authenticated
   reload; anonymous recruiter-access denial; and used invitation refusal.

No private identities, message bodies, bearer links or screenshots are committed.
Ignored locator: `data/self-scheduling-current.json`; corresponding private test
directory contains results, synthetic screenshots, fake mail and ownership evidence.

## Confirmed defects and minimal corrections

**Joining configuration:** a new regression failed before the fix because
`self_scheduling.book` reached booking writes without checking LiveKit configuration,
unlike the ordinary recruiter invitation route. The correction uses the existing
`livekit_configuration()` contract after authorization and slot validation, before
booking/invitation writes or SMTP. Missing configuration now returns sanitized 503
without consuming the invitation. This is configuration validation, not a live
provider health check; a configured server can still be unreachable.

**Misleading UI:** the candidate page said “No email delivery yet” even when the
existing email workflow was enabled. It now explains that email status appears
after booking and acceptance is not proof of delivery. No consent or access rules
changed.

## Validation

- **16 backend tests passed, 0 skipped**: self-scheduling contracts, email templates
  and allowlist, fake acceptance/failure/timeout, durable uncertain state, real
  PostgreSQL competing bookings/manual-booking race, duplicate prevention and a
  new authenticated API workflow. The latter covers wrong/stale selection, foreign
  recruiter and anonymous access, expired/unknown invitation, exact confirmation
  times/link association, conflicts, reload and interrupted-send suppression.
- The new authenticated test initially passed alone but failed after a prior
  `TestClient` loop reused a cached async pool. Its test-only session factory now
  uses the current loop's real PostgreSQL engine; no authorization is mocked.
  The combined 16-test run passed. The initial missing-configuration regression
  failed as expected before the production correction.
- **19 focused frontend tests passed**: invitation controls, protected requests,
  bearer removal, corrected text, booking notice, recruiter review/navigation,
  stale/foreign selection and duplicate/uncertain-write handling.
- TypeScript and production frontend build passed. Existing large-chunk advisory
  remains; no bundling redesign was attempted.
- **13 additional invitation-security tests passed**, covering single-use claims,
  expiry/rotation, join-window boundaries, throttling, owner checks and revocation
  with fake provider interfaces. **29 distinct backend tests passed in total**;
  repeated preliminary runs are not added to this count. Whitespace checks passed.

## Remaining gaps

Available slots remain explicitly synthetic: fixed 60-minute Asia/Dhaka office
rules, weekdays over 14 days. This is not general calendar availability.
The manual recipient must be explicitly allowlisted; this flow does not prove
mailbox ownership or automatically validate an imported application's contact.
Bulk trusted-contact preview and recruiter-booked appointment email remain separate.
There is no automatic resend after accepted, failed, uncertain or interrupted
recorded sends. Native candidate confirmation recovery after refresh, real email
delivery/public origins and live joining require separate acceptance or a reviewed
follow-up. No new external trial is justified by this acceptance alone.

The test-owned frontend, API and PostgreSQL were stopped after acceptance. Their
named volume and all ignored evidence remain. The three working Groq container
identities and start times matched the preflight snapshot after cleanup.
