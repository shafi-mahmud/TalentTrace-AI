# Recruiter application analytics

## Implemented service

The authenticated job applications API reconciles local validated upload files
with the trusted external-import ledger using `(batch_id, upload_id)`. An imported
file present in both stores counts once as a trusted import. Scoring tables are
not read and running screening cannot create another received application.

New means this job/application identity has not been explicitly marked viewed.
Acknowledge requests contain only the displayed identities. The service validates
that snapshot against current identities and inserts acknowledgement rows with
conflict handling; repeat acknowledgement is safe. Later arrivals stay new.
Native files that have disappeared cannot be historically counted without an
intake ledger; imported identities remain counted with unavailable-file warnings.
File availability checks type/size/signature, not a fresh cryptographic digest.

Ownership is checked before discovery or acknowledgement. No CV text, filenames,
contact data, external source IDs or credentials are returned. Listing is bounded
to 1,000 identities; exceeding bounds fails instead of returning partial totals.
Invalid native batches are excluded with a warning. These are local workspace
counts, not counts from a live Google Forms or LinkedIn query.

## Migration compatibility and verification

The existing `0011_application_views` migration is reused unchanged; the single
head at that historical checkpoint was `0016_submission_deletion`. No migration was executed against
an existing database. The model is registered in the current backend.

Initial service validation: 12 backend tests passed, one opt-in disposable
PostgreSQL test skipped; 3 frontend API tests passed. Authorization tests use real
authentication/ownership handlers with SQL doubles; acknowledgement tests use
statement doubles. PostgreSQL concurrency/durability acceptance is not inferred
from those doubles. No external calls were made.

## Implemented Home dashboard

Select an active saved job on Home. Only that job's application API is requested.
Its title and persisted Job Reference identify the analytics panel. Cards show
received, new/unviewed, viewed, and available totals. Unavailable CVs are flagged separately. Source counts
and accessible meter bars distinguish native storage from trusted imports.
Continue to Candidate Screening carries the exact selected job.

Loading/error states do not substitute zero. A retained snapshot during refresh
or after failure is explicitly labelled stale. Refresh is manual, without polling.
Neither loading, opening nor refreshing marks applications viewed. The explicit
acknowledgement sends only the displayed snapshot (initially 25, with Show more
in steps of 25, bounded by the service's 1,000). Duplicate clicks are guarded;
an unconfirmed acknowledgement requires refresh before another attempt. Job keys
and request-generation fences keep late responses out of another job's panel.

The list exposes ordinal labels, source category, availability and viewed status,
not CV text, contacts, filenames or external identifiers. It is in stable identity
order, **not chronological order**. A reliable cross-source arrival timestamp is
not available in the existing API, so a genuinely recent-arrival list remains
unavailable. No filesystem dates are used.

Complete current-revision screening analytics also remain unavailable: the saved
scores endpoint is revision-bound but does not contain the complete operational
failure history of all submitted applications. It cannot honestly produce the
requested five-category summary for the received population. These limitations are documented here rather than added as implementation prose
to the dashboard. No historical
revision totals, conversion rates or predictive metrics are invented.

## Files and final verification

- Backend route registration, model registration and reused notification
  service/router/model: `app/api/router.py`,
  `app/api/routers/application_notifications.py`, `app/db/models/__init__.py`,
  `app/db/models/application_view.py`, `app/services/application_notifications.py`.
- Backend tests: `test_application_notifications.py` and
  `test_notification_integration.py`.
- Frontend: `api/applications.ts`, `components/RecruiterHome.ts`,
  `components/ApplicationNotifications.ts` and `index.css`.
- Frontend tests: `applications.test.ts` and `dashboardApplications.test.ts`.

Run all frontend Node tests, TypeScript app/node checks, and the production build.
Run backend notification/integration, CV upload, external-intake and bridge tests.
The responsive implementation uses the existing design tokens, wrapping and an
auto-fit card grid; live browser/mobile viewport acceptance was not performed.
No existing service was deployed or restarted. The normal existing large LiveKit
bundle warning is unrelated to these analytics changes.

Recommended follow-up: authorize an isolated synthetic browser/DB acceptance of
refresh, acknowledgement persistence, late arrivals and desktop/mobile layouts.
Timestamped native intake history and complete screening-failure persistence would
be separate future requirements, not implied by the current counters.

Final combined results: **277 frontend tests passed, 0 failed/skipped; 95 backend
tests passed, 0 failed, 3 skipped**. The skipped cases are the opt-in PostgreSQL
notification, external-intake and bridge integrations. TypeScript app/node checks,
Vite production build and Git whitespace checks passed. The initial service-only
counts above are a subset of these totals, not additional tests.

## Trainer feature status — finalization, 25 October 2026

**Implemented:** recruiter Home dashboard for one explicitly selected owned job,
using the existing authenticated application API. Branch
`feature/recruiter-analytics-finalization`, based on develop `cba35ab`.

- Compact cards show received, new/unviewed, viewed and available CV counts.
  Viewed is exactly received minus unviewed, not a claim that a CV was read or scored.
- All/New/Viewed filters operate on the validated job-scoped snapshot. Switching
  filters or refreshing never acknowledges anything. Acknowledgement uses only
  the displayed identities; filters reset the display limit to 25. Later arrivals
  remain new. Viewed-only and empty selections cannot trigger acknowledgement.
- Zero applications has a short empty state without unused filters/list actions.
  Unavailable files and invalid batches retain short warnings; loading failures
  do not become zero and retained snapshots are labelled out of date.
- The existing Job Reference, source deduplication, owner checks, request fences,
  explicit acknowledgement, and source breakdown are reused unchanged.
  No candidate PII, filenames or provider data are added. Mobile cards use a
  two-column compact grid; keyboard-operable filters expose aria-pressed state.
- Verbose implementation explanations were removed from the interface. No arrival
  dates, screening outcomes, conversion/hiring rates, candidate quality, email
  alerts, cross-job totals or background polling are claimed.

No backend service, API contract, database schema, migration or runtime change was
needed. Current integrated schema head remains `0017_booked_interview_email`.
The separate trainer UI finalization and F3/F4 branches are preserved; this feature
starts from develop and does not silently incorporate their unmerged changes.

Validation results are recorded below. Browser desktop/mobile visual acceptance
and new live PostgreSQL acceptance were not performed in this increment. Existing
PostgreSQL evidence is historical; SQL doubles are not a database durability proof.

Finalization verification: **305 frontend tests passed, 0 failed/skipped**;
focused notification backend **14 passed, 1 skipped**. The skipped case is the
explicit opt-in PostgreSQL notification acceptance test; it was not enabled.
Three new frontend cases cover filtering/acknowledgement, filtered pagination and
compact zero state. Two new backend cases cover cross-batch identity and repeated
ledger deduplication, plus viewed/unavailable import versus new-native counts.
The existing real-auth route test additionally rejects anonymous acknowledgement.
An initial focused assertion still expected the removed unavailable metric card;
it was corrected to assert the new Viewed total before the passing final runs.

TypeScript app/node checks and Vite production build passed; existing >500kB
LiveInterviewPage chunk warning remains. Git whitespace checks passed. No external
requests, Docker operations, database reset, migration, merge or push occurred.
