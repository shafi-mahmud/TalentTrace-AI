# F4 transcript integration

Development branch: `feature/f4-transcript-storage-integration`, base `2a4a15b`.
Original worktrees and demo databases are unchanged. Activation is opt-in using
`TRANSCRIPT_STORAGE_ENABLED=true`, after reviewed migrations through
`0013_transcript_lifecycle`. No audio/video files or external AI evaluation are
authorized. The approved text-storage wording remains version
`optional-transcript-storage-v1`.

## Implemented privacy lifecycle

The schedule has no actual interview-completion timestamp. The conservative
policy is an immutable retention deadline of 30 days after first authorized
capture creation, capped by the persisted scheduled end. Capture creation
precedes any stored text; using that earlier point deliberately deletes sooner
than 30 days after interview completion. It is not claimed to be an actual
completion timestamp. Migration 0013 backfills existing foundation captures using
their earliest persisted creation time, capped by scheduled end.

Reads, writes and session creation deny expired content synchronously under the
existing interview-row privacy lock. Delayed physical cleanup cannot reopen it.
Withdrawal and cleanup permanently retain the interview-level revocation marker.
Deletion first commits that fence, then atomically deletes turns before captures,
verifies absence and commits `deleted` plus the verification timestamp. Failure
is `failed` or remains pending/unavailable, never falsely verified. Concurrent
cleanup serializes on the interview. Explicit retries are idempotent. Minimal
schedule tombstone and hashed privacy credentials contain no transcript text.

Enabled application startup runs a bounded cleanup sweep immediately and every
`TRANSCRIPT_CLEANUP_INTERVAL_SECONDS` (default 60). It processes at most 20
interviews per sweep, tolerates competing workers and retries failed/pending
cleanup on later sweeps. Each transaction retains existing five-second total,
three-second statement and one-second lock limits. No queue or separate service
is introduced. During downtime, read denial remains effective when the app
returns, and the immediate startup sweep resumes deletion. Keep an enabled
worker running until outstanding cleanup finishes even when live storage is
otherwise paused. Operational state is sanitized; no exception SQL/text is logged.

An independently authenticated candidate can obtain a privacy-only HttpOnly
cookie during the join window. Only its hash, interview association and expiry
are stored. It grants withdrawal/status access, never transcript retrieval,
scores or joining. It remains usable after invitation/join expiry until one day
after retention expiry. The owning recruiter's regular authenticated session can
also withdraw after the interview without requiring unchanged screening criteria.
Mutation/origin protection remains required. Losing all candidate credentials
requires recruiter-assisted deletion; no account-recovery identity is invented.

## Migration safety

The chain is `0010_interview_transcripts -> 0011_application_views ->
0012_transcript_privacy_guard -> 0013_transcript_lifecycle`. The copied 0011 remains
the exact notification dependency, without notification functionality. Only
disposable PostgreSQL test databases are upgraded/downgraded here. Later demo
activation requires a verified private backup, database identity check, deliberate
`alembic upgrade 0013_transcript_lifecycle`, restart with the feature opt-in, and
synthetic verification. Do not downgrade an activated database: removing privacy
columns destroys retention/revocation history.

## Integration verification status

Phase A privacy enforcement and Phase B's opt-in trusted caption adapter are
implemented. No current live demo was activated by this development session.
Mocked microphone/STT tests do not prove physical-device performance or accuracy.

## Trusted final turns and normal finalization

Only validated final output from the existing local tiny.en worker enters
`CaptionTranscript`; no endpoint accepts browser transcript text. Text events
have deterministic UUIDv5 identities from capture UUID and caption sequence.
Repeated identical events reconcile through the existing unique keys. There is
no text queue and no automatic retry after a persistence failure/uncertain commit.
Storage failure does not stop ordinary temporary captions.

Normal finish preserves the browser flush, per-role end acknowledgement, bounded
pending chunk drain and final-caption exchange. The adapter waits for each
database acknowledgement. Capture completion also compares actual persisted turn
count with expected/acknowledged events and validated accepted/processed sample
evidence. Calling `finish_session(completed=True)` without evidence is rejected.
Empty recognized speech is legitimate silence, not a missing text turn. Outcomes
remain incomplete/unconfirmed when processing, delivery or persistence fails.
Summaries certify accepted audio only, never all speech or ASR accuracy.

An already authorized active capture can obtain one non-extending, persisted
35-second finalization deadline before its join window closes. Trusted final
writes may use this deadline and the immutable interview context after the window;
they never reopen a room or create a general post-interview text-writing API.
Existing caption sockets can drain only within that bound, with fresh owner and
invitation-revocation checks. A new socket still needs the normal join window.
Revocation/retention remain authoritative throughout. Timestamps are server chunk
interval estimates, not word-level alignment. Caption consent withdrawal and
disconnect remain immediate audio discard, not graceful drain.

Phase B validation: 105 focused transcript, privacy, consent and caption tests
passed, including disposable PostgreSQL full/residual final-turn storage,
completeness verification, privacy deletion, storage failure isolation and bounded
post-window writes. No raw media files, cloud calls or physical microphones were
used. Frontend consent and retrieval follow in Phase C.

## Consent UI and API

Phase C adds a separate optional-storage panel to the existing interview page.
Nothing is checked automatically. Both participants review the same approved
wording, independently accept, then start normal caption consent. Storage
acceptance after caption capture starts is refused: existing pre-consent buffered
audio must never become stored text. Decline keeps captions usable and permanently
disables storage for this interview. The panel distinguishes authorization from
confirmed saved text, incomplete/unconfirmed storage and verified deletion.

The candidate can bookmark `/transcript-privacy` in the same browser for later
withdrawal. Its HttpOnly privacy cookie is a separate withdrawal-only credential;
the URL contains no bearer. It does not grant access to transcript text or room
tokens. Owning recruiters use the saved interview page to review or withdraw
without joining. Review uses React text rendering, chunk-level speaker/time
labels and completeness warnings. No transcript content enters localStorage.
Status polls are GET-only; POST requests are never automatically retried.
Withdrawal clears displayed text immediately in the requesting panel; other open
review panels clear it when their next status poll observes revocation/expiry.
Previously delivered text cannot be recalled. All new backend reads are denied
immediately once withdrawal commits.

Actual endpoints, prefixed `/api/v1`:

- `GET /transcript-storage/config`: opt-in availability and approved disclosure.
- `POST /jobs/{job}/interviews/{interview}/transcript-storage/prepare`: `{}`,
  authenticated recruiter; returns the server capture UUID and disclosure version.
- `POST /interview-access/transcript-storage/prepare`: same, using candidate cookie.
- Corresponding `/decision` POSTs: `{capture_id, decision: "accept"|"decline"}`.
  Accept requires the exact `X-TalentTrace-Storage-Consent` version header.
- `GET /jobs/{job}/interviews/{interview}/transcript-storage/status`: authorized
  privacy/metadata status and sanitized cleanup-worker state, no text.
- `POST /jobs/{job}/interviews/{interview}/transcript-storage/withdraw`: `{}`.
- `GET /interview-transcripts/privacy/status` and POST `/withdraw`: candidate
  privacy-cookie boundary, server-resolved interview; no supplied owner/role IDs.
- `GET /jobs/{job}/interviews/{interview}/transcript?limit=100&offset=0`: recruiter-only
  bounded turns, capture outcomes/evidence and chunk-estimate warning. Maximum
  page size 200; `next_offset` is a conservative next-page hint.

All mutations retain `X-TalentTrace-Request: 1`, cookie and origin protection.
There is no endpoint accepting transcript text, client consent receipts or
candidate-supplied role/owner. Errors use fixed sanitized codes and uncertain
outcome flags. Disabled storage returns 404 on feature operations. Existing API
no-store middleware and credentialed same-origin/proxy routing remain required.
The API and caption WebSocket must use the same single caption-worker process
for pending consent/capture RAM; durable revocation/deletion remain cross-process.
No cross-worker audio recovery or shared pending HMAC receipts are claimed.

Phase C frontend validation: 176 tests, TypeScript and production build passed.
The existing LiveKit bundle-size warning remains nonblocking. No interview was
booked, model invoked or production/development demo process restarted.
