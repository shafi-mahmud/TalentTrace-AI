# F3 increment 1 — recruiter selection and scheduling

## Implemented — separate recruiter scheduling workspace

Use **Interview Scheduling** in the top navigation, or
`/#interview-scheduling`. Candidate Screening keeps requirements, scores,
evidence and **Select for interview**, plus **Go to Interview Scheduling**.
Selection transfers the current job, batch and candidate in memory. The page
reuses the existing individual invitation, bulk preview/confirmation/status,
manual booking and saved-interview components and APIs.

The active job UUID is remembered per recruiter in session storage and reloaded
through the owned-jobs API after refresh. Candidate selection is not persisted;
reload saved scores to select again. Foreign, stale or unconfirmed selections
are discarded. Candidate `/interview-schedule` and `/interview-join` routes are
unchanged. Navigation alone sends no invitations or booking requests; retained
bulk operation status and saved interviews may be fetched read-only.

## Implemented

Eligible cards in screening results offer **Select for interview**. The recruiter
enters a future local date/time, selects an IANA interview timezone and duration,
then schedules. The timezone defaults to the browser zone but can be changed.
No AI selection/new workflow is added; screening and scores remain unchanged.
Eligible-but-unscored candidates show a warning and require an extra explicit
acknowledgement. Excluded, incomplete and failed candidates cannot be selected.

Owned `POST /api/v1/jobs/{job_id}/interviews` accepts batch/upload references,
current criteria revision/scoring version, explicit confirmation and schedule
fields. The server locks the owned job and rereads current approved F2 records.
Client qualifications, decisions, scores and meeting URLs are forbidden. Foreign
jobs return 404; stale/unapproved/noneligible records return controlled errors.
Owned `GET /api/v1/jobs/{job_id}/interviews` lists up to 100 saved schedules.

Migration `0004_interview_schedules` adds one provider-independent table containing
UTC start, IANA timezone, duration, job/recruiter/batch/upload references,
criteria/scoring version and a validated selection snapshot. Upload UUID is the
candidate reference, not a claim that native candidate identity exists. No score
row FK is added: F2 replaces those rows on rerun; the copied evidence preserves
the decision reviewed at scheduling time.

One initial interview per job/batch/upload is enforced by database uniqueness,
independent of later revisions. A job row lock serializes concurrent selection
against edits/reruns. Duplicate requests return 409; there are no automatic POST
retries. After uncertain delivery, reload saved interviews before another attempt.
Reuploads with new identities are not automatically deduplicated.

**Implemented — local-time entry:** the frontend resolves the entered wall-clock
minute in the selected IANA timezone and submits the existing UTC `scheduled_at`
plus `timezone` fields. Both the preview and saved history show local time and UTC.
The machine's timezone is only a default; it never overrides the chosen zone.
Invalid dates, past times, daylight-saving gaps and repeated local times are
rejected with a controlled explanation. For repeated times, choose another
unambiguous time; selecting the first/second occurrence is not implemented.
Conversion uses the browser's IANA timezone data and minute resolution, with a
bounded search across UTC offsets and exact local-time round-trip validation.
Keep browser timezone data current. No timezone library or API/schema change
is required. Python's
standard `zoneinfo` validates zones; installed `tzdata` is explicitly pinned for
Windows portability. Duration 15–180 minutes/default 30 are implementation
bounds/convenience, not confirmed BID/trainer policy. Existing schedules remain
historical after criteria edits; they are not silently cancelled or reapproved.

Schedules/evidence are privacy-sensitive. No candidate contact, token, calendar
credential or meeting secret is included. Existing authentication, ownership,
CSRF and sanitized errors apply. Production retention/governance remain separate.

## Verified and boundaries

On 12 October 2026, fresh disposable localhost-only pgvector PostgreSQL reached
0004. Actual FastAPI routes via in-process HTTP transport, real password/cookie
authentication and PostgreSQL write/read verified scored selection, explicit
unscored selection, UTC, foreign/stale/excluded rejection and concurrent duplicate
requests returning exactly 201/409. Downgrade to 0003 and re-upgrade passed.
The office demo database was not migrated.

Saved screening fixtures for this F3 check used existing validated screening/scoring
helpers; this was not another real-provider CV run. Automated backend/schema and
frontend validation/rendering tests supplement it.

**Verified — 12 October 2026:** a separate fresh isolated PostgreSQL instance and
temporary ports 8004/5177 supported real browser login, manual criteria confirmation,
synthetic DOCX/PDF intake and actual Groq-backed screening. Eligible-but-unscored
selection required the warning checkbox; excluded and unavailable sources could
not be selected. Scheduling persisted 09:00 UTC / 15:00 Asia/Dhaka and 45 minutes.
Real API checks confirmed foreign 404, stale/excluded/incomplete/unconfirmed and
duplicate 409, plus concurrent create responses 201/409. No provider was mocked.

The browser identified and fixed one integration defect: saved schedules were
previously hidden after full reload because the panel required in-memory screening
results. History now loads for the active owned job independently of those results.
Full reload and later criteria edits retained visible historical schedules, and a
second recruiter could not see the first recruiter's job/history. Whole CV-batch
workspace restoration remains separate from schedule-history retrieval.

## Manual verification — isolated environment only

1. Approve migration to 0004 in a separate development DB. Start this branch's
   backend/frontend on unused ports with matching proxy/trusted origin.
2. Sign in, confirm job criteria/weights and screen synthetic CVs. Select an eligible
   card, enter a future local time and select the interview IANA zone, then schedule.
   Check the local/UTC preview, saved display, UTC API value and reload persistence.
   Change the selected zone away from the browser default and verify conversion.
   Try a DST gap/overlap: the UI must reject it without a POST.
3. Verify unscored acknowledgement, no selection on excluded/failed cards, duplicate
   rejection and foreign-recruiter 404. Edit criteria: reject old screening records
   for new selection while keeping historical schedules visible.

## Planned

Rescheduling/cancellation, multiple rounds, wider duplicate/calendar-conflict
detection, verified candidate accounts, Google Calendar,
email, recording and transcription. Expiring candidate bearer invitations and
two-role LiveKit joining are implemented for synthetic development testing in
[Interview invitations](interview_invitations.md). Scheduling is not a hiring
decision and sends no external message.

## Local-time increment verification

Automated conversion tests cover Asia/Dhaka, Nepal fractional offsets, UTC,
New York winter/summer offsets, date rollover, invalid/past dates, DST gaps and
overlaps (including Lord Howe half-hour transitions and an Apia skipped date).
Frontend tests verify timezone selection, local/UTC preview, controlled DST
messages, preserved unscored acknowledgement and the unchanged API payload.
Existing backend scheduling/authorization and invitation/LiveKit tests are
regression checks; no new live browser or database verification is claimed for
this frontend increment. Existing demo services and PostgreSQL data remain intact.

Validation: 126 frontend tests and 40 backend interview/access/LiveKit tests passed;
frontend production build passed. No provider call or migration was required.
