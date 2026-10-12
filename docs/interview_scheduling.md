# F3 increment 1 — recruiter selection and scheduling

## Implemented

Eligible cards in screening results offer **Select for interview**. The recruiter
enters a future UTC start, IANA display timezone and duration, then schedules.
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

UTC input is deliberate: IANA timezone controls display only, avoiding silent
interpretation of daylight-saving overlaps/nonexistent local times. Python's
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
   card, enter future UTC time and valid IANA display zone, then schedule. Check
   saved local display, UTC API value and reload persistence.
3. Verify unscored acknowledgement, no selection on excluded/failed cards, duplicate
   rejection and foreign-recruiter 404. Edit criteria: reject old screening records
   for new selection while keeping historical schedules visible.

## Planned

Rescheduling/cancellation, multiple rounds, wider duplicate/calendar-conflict
detection, candidate authentication/public meeting links, Google Calendar,
email, recording and transcription. No candidate meeting URL is invented.
The recruiter-only [LiveKit synthetic proof](livekit_interview_proof.md) is now
implemented separately on current owned schedules. Scheduling is not a hiring
decision and sends no external message.
