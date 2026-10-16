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

## Recovery, boundaries and verified rehearsal

The single caption worker and both API roles were exercised against disposable
PostgreSQL through the actual authenticated HTTP and two caption WebSockets.
Both participants explicitly accepted, a mocked local worker processed synthetic
PCM, normal finish flushed the residual chunk, the committed turn was retrieved
by its owning recruiter, and candidate withdrawal caused read denial and verified
physical text/session deletion. This is an automated synthetic integration test,
not a physical-device/browser or real Whisper accuracy verification of this branch.

Persisted recognition-start metadata distinguishes late caption starts from
abandoned consent. The enabled maintenance task marks an active capture stale
after ten minutes without a supported continuing capture (the maximum capture
is 300 seconds plus bounded finalization). It becomes interrupted/partial or
failed; unknown sample completeness is never reconstructed. A fresh explicitly
reviewed handshake can create a new capture after closure. Expired pending
receipts can be replaced only by explicit fresh review, with a new capture UUID
and both participants' new acceptance; decide does not silently renew receipts.
No RAM audio is recovered after restart. Pending negotiation still requires the
same backend worker; privacy checks remain durable across processes.

Cleanup scans use a bounded, rotating in-memory cursor so persistent failures
cannot monopolize the first page. Restart resets only that scan position, never
privacy authorization; the scanner wraps and retries durable pending/failed rows.
Inactive recruiter accounts do not prevent automatic deletion or a previously
authenticated candidate's privacy-cookie deletion request. Candidate credentials
remain limited to privacy status/deletion and never permit transcript reads.

Normal end sends the separate storage acknowledgement before `stopped`. The UI
waits rather than interrupting an already authorized bounded drain when the join
window expires. Network failure, capture failure or consent withdrawal still
abort caption audio immediately. Storage-only withdrawal leaves temporary captions
usable. Saved timestamps are chunk estimates relative to capture authorization,
which may precede microphone start; they are not word-level or interview-start
alignment. Delivered text cannot be recalled; displayed review is cleared on the
next privacy status check if another participant withdraws.

Known deployment limits: one single-room caption worker; at most 100 in-memory
pending interview entries per process, bounded audio buffers, 120-second normal
caption cap (up to 300 in the existing isolated test mode), 35-second server drain,
40-second browser wait, and no durable audio/text retry queue. Cleanup must remain
enabled/running after activation until all outstanding records have been deleted.
If storage/cleanup is unavailable, synchronous privacy checks fail closed and
deletion is not reported complete. Retention access denial is immediate even while
physical deletion is waiting for a healthy database/worker. Backups, exported
copies and previously delivered text are outside this application's verified
row-deletion claim and need deployment-specific handling before production use.
No production activation, new disclosure to AI providers or F5 evaluation occurs.

## Safe reproduction

For the automated test, in this worktree's `backend` directory, use the existing
Python environment with pinned project dependencies and Docker:

```powershell
$env:TRANSCRIPT_PG_TEST = '1'
python -m pytest tests/test_interview_transcripts.py::test_pg_two_authenticated_websockets_consent_to_saved_review_to_deletion -q
```

The fixture asserts loopback port 54402 and the disposable `transcript_test`
database; it creates/removes its own container and never migrates ports 54378 or
54379. Other transcript/retention tests use the same explicit convention. The
legacy mocked MCP tests need a local ignored MCP Python executable; this session
created an interpreter-only `.venv` in this worktree, without publishing, network
installation or changes to the preserved original MCP edit.

For a later manual check, first obtain separate approval for any demo database
activation. Prefer a new isolated synthetic database and private configuration.
Verify identity/backup, then explicitly upgrade that target to
`0013_transcript_lifecycle`. Keep `INTERVIEW_EMAIL_ENABLED=false`. Configure
`TRANSCRIPT_STORAGE_ENABLED=true`, existing tiny.en/LiveKit settings and exact
frontend origin; use unused loopback ports. Existing Vite defaults proxy `/api`
to localhost:8000; either use a dedicated backend there after checking availability
or set `VITE_API_BASE_URL` to the selected backend and allow that exact frontend
origin. Preserve other running services.

In the browser, open the synthetic saved interview. Both participants join using
their own existing authorization, review the storage disclosure and independently
accept before starting caption capture. Both then consent separately to captions.
Speak synthetic text, choose normal finish/Leave, and check the storage outcome.
The recruiter loads the saved transcript from that interview's optional panel;
historical criteria revisions retain a separate transcript/privacy navigation
action. The candidate uses `/transcript-privacy` in the same browser to withdraw
later. Verify deleted status and denied recruiter retrieval. Never interpret an
unconfirmed/incomplete outcome as a complete interview transcript.

## Changed-file inventory relative to 2a4a15b

### Independent final verification — 16 October 2026

Verified baseline: clean `ca1f0af`, with one Alembic head
`0013_transcript_lifecycle`. The 135 focused backend tests passed again against
disposable PostgreSQL, including upgrade/downgrade/re-upgrade, cross-process
revocation, both write/withdrawal lock orders, cleanup retries, restart recovery,
foreign-owner denial and incomplete-finalization handling. Frontend: 177 passed;
TypeScript and production build passed (existing bundle-size warning only).

An additional private, ignored verification harness reused the authenticated
HTTP/two-WebSocket integration test with the actual `LocalWhisper` subprocesses
and installed CPU int8 tiny.en model. It replayed 3.9 seconds of existing Windows
SAPI synthetic benchmark audio per role, in paced PCM frames with the same
one-second heartbeat used by the browser. Both speaker roles produced saved
turns, normal finish drained residual audio, the owning recruiter retrieved a
completed capture, and candidate withdrawal verified deletion and denied reads.
The final real-worker and retention-boundary checks both passed. The initial
harness lacked heartbeats and disconnected during model startup; correcting the
harness required no application changes. All test containers were disposable.

This is real local STT through ASGI HTTP/WebSockets and PostgreSQL, **not** a
browser, LiveKit media, physical-device or microphone test. Those parts of the
new storage integration remain unverified. Earlier physical temporary-caption
verification does not establish browser verification of this branch.

The exact immutable deadline is `min(first authorized capture time, scheduled
end) + 30 days`; the scheduled end caps the **anchor**, not the final deadline.
The extra PostgreSQL check verified readable text after scheduled end and until
one microsecond before the deadline, then denied access and verified cleanup at
expiry. This intentionally conservative policy promises a maximum, not 30 full
days of availability after actual completion. No premature interview-end expiry
or critical implementation defect was found; no corrective code commit was made.

Integration inspection: local `develop` is `2cd7536` and is an ancestor, with
54 commits on this branch and none unique to `develop`. Seven transcript commits
follow original F4 `e0c859e`, from `7a4fd57` through `ca1f0af`. Preserve their order
and migrations 0010–0013; do not cherry-pick only the final commit. Migration
0011 has the identical Git blob `3b85b5a` in the notification branch (working-copy
line endings differ), so later integration must retain one copy of that revision.
Notification router/model registration and separate LinkedIn publishing changes
still require integration review; no merge/conflict-resolution run was performed.

Recommended activation remains: reviewed integration branch, combined regressions,
verified target database/backup, approved migration through 0013, private model
and LiveKit configuration, exact frontend origin/cookies, explicit storage opt-in
and one backend worker. Keep email disabled and cleanup running. Complete a fresh
two-browser consent/save/review/withdrawal rehearsal before declaring this storage
UI demo-ready. Production additionally needs backup/export retention handling,
candidate credential recovery policy and operational deletion monitoring. F5
evaluation and external-AI disclosure remain separate, unimplemented work here.

Final verification on 16 October 2026: full backend suite 1,278 passed and 12
skipped; final affected transcript/privacy/caption/access/LiveKit suite 135 passed
after the last recovery/privacy changes. Frontend 177 passed, none skipped;
TypeScript, production build, Python compilation and diff checks passed. The
full backend's initial three MCP publication-test failures were resolved by
provisioning only its ignored local interpreter prerequisite, not by changing
publishing code or weakening tests. Optional unrelated environment-gated checks
remain skipped. No real publication/email/cloud operation was performed.

- Configuration/runtime: `.env.example`, `backend/app/core/config.py`,
  `backend/app/main.py`, `backend/app/services/transcript_runtime.py`.
- Schema/models: `backend/alembic/versions/0013_transcript_lifecycle.py`,
  `backend/app/db/models/recruiter.py`, `backend/app/db/models/interview_transcript.py`,
  `backend/app/schemas/interview_transcript.py`.
- HTTP/WebSocket: `backend/app/api/router.py`,
  `backend/app/api/routers/transcript_storage.py`,
  `backend/app/api/routers/interview_captions.py`.
- Services: `backend/app/services/transcript_privacy.py`,
  `backend/app/services/interview_transcripts.py`,
  `backend/app/services/transcript_consent.py`,
  `backend/app/services/caption_transcript.py`,
  `backend/app/services/interview_captions.py`.
- Frontend: `frontend/src/App.tsx`, `frontend/src/api/transcripts.ts`,
  `frontend/src/components/TranscriptPanel.tsx`,
  `frontend/src/components/InterviewCaptions.tsx`,
  `frontend/src/components/LiveInterviewPage.tsx`,
  `frontend/src/components/InterviewScheduling.ts`.
- Tests: `backend/tests/test_interview_transcripts.py`,
  `backend/tests/test_transcript_consent.py`,
  `frontend/tests/transcriptStorage.test.ts`,
  `frontend/tests/interviewFinalization.test.ts`.
- Documentation: this guide and `docs/interview_transcript_foundation.md`.
