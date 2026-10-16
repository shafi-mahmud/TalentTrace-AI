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

Phase A privacy enforcement is implemented. Live transcript writer and UI are
being added in subsequent milestones in this branch. No current live demo was
activated by this development session. Mocked microphone/STT tests do not prove
physical-device performance or speech-recognition accuracy.
