# Interview transcript persistence — foundation and consent integration

## Increment 2B-1: durable revocation guard (implemented, inactive runtime)

This increment is based on `bab21e8`, in the independent
`feature/f4-transcript-privacy-guard` worktree. The sections below headed 2A and
Increment 1 describe earlier versions; their process-only limitations are
superseded here specifically for revocation and guarded application reads/writes.
There is still no live transcript writer, saving API or frontend storage control.

### Migration and durable state

The exact `0011_application_views` migration was copied from the notification
worktree as an ancestry dependency only. No notification service, model, route
or UI was integrated. Its `job_profiles` foreign-key dependency already exists.
The new linear graph is:

`0010_interview_transcripts -> 0011_application_views -> 0012_transcript_privacy_guard`

Revision 0012 adds only nullable, timezone-aware
`interview_schedules.transcript_storage_revoked_at`. NULL means no recorded
withdrawal, never affirmative authorization. A non-NULL timestamp is permanent
through normal application operations and applies to every capture for that
interview, even if withdrawal happened before a capture existed. No index is
needed beyond the existing interview primary key. The marker is not deleted
when a capture is cleaned up or eventually physically deleted.

The copied 0011 has the same revision, filename and content as the existing
notification migration. Later integration must coalesce that identical migration,
not generate another 0011, rewrite its parent, or recreate `application_views`.
This worktree has one Alembic head. No branch merge was performed.

Only disposable test databases receive these migrations in this increment.
Downgrading 0012 removes withdrawal history and is unsafe for an activated storage
system without a separately approved data/privacy recovery plan; test rollback
is not permission to downgrade a demo or production database.

### Consent and withdrawal flow

The existing recruiter session/owned-job checks or independently claimed candidate
invitation session, mutation protection, current criteria and join window are
reused inside `StorageConsentAuthority._participant`. Approved wording and HMAC
receipt checks are unchanged. Pending receipts, HMAC signing keys and capture
negotiation remain process-local; this increment does not implement cross-process
sharing of pending consent or make receipts survive restart. Positive session
consent metadata is durable as before. Every new authorization operation checks
the durable marker; NULL alone never creates a session.

`StorageConsentAuthority.withdraw` authenticates the actual participant, locks and
refreshes the interview row, writes the marker only if NULL and commits it in its
own bounded transaction. Duplicate withdrawals retain the original timestamp.
Withdrawal does not require a local coordinator entry, capture receipt or a known
capture ID: it revokes the authenticated interview, not a client-selected capture.
The coordinator commits this marker before clearing receipts or attempting
interrupted session metadata cleanup. Cleanup failures cannot roll it back or
reset it. A fresh process observes the same marker. The local revoked-ID set is
only a fast-rejection optimization, never the durable source of truth.

The coordinator reports `withdrawal_committed` only after commit acknowledgement.
If acknowledgement is lost, the transaction error remains explicitly uncertain;
no cleanup or automatic retry is issued. Reconcile the database first. A fresh
coordinator with no local capture reports metadata cleanup pending rather than
trusting a supplied capture ID. `deletion_verified` remains false, including when
metadata closure succeeds. Metadata closure is not physical deletion.

### Locking and application access protection

All transcript service operations acquire the owned interview row lock before
capture row locks and hold it until transaction completion. Capture operations
first perform a nonlocking, owner-scoped parent identity lookup, then lock and
refresh the interview and finally lock/refresh the capture. Existing participant
authentication takes its job lock before the interview lock; persistence does
not acquire a job lock after taking an interview lock. This avoids reversing
the existing authentication lock order. Authorization checks after lock waits
use refreshed ORM state rather than cached NULL markers.

The durable marker is checked before:

- New or repeated session creation.
- New final-turn insertion and duplicate-event reconciliation (including returning
  an already saved identical event).
- Bounded transcript retrieval.
- Completed/saved session finalization.

Interrupted metadata cleanup is allowed for the owning recruiter-scoped internal
service after withdrawal. It cannot insert turns, return their text, clear the
marker or declare deletion complete. No public endpoint was introduced.

Race semantics are deliberate: a write which obtains the interview lock first
can commit before withdrawal. Withdrawal then commits and hides that stored text.
If withdrawal obtains the lock first, the write waits, observes the non-NULL marker
and fails. Thus no transcript service write can commit after an already committed
withdrawal. Reads serialize on the same row: new reads after withdrawal fail.
An authorized read that precedes withdrawal may already have delivered text;
previously returned objects, copies or text shown to a user cannot be recalled.
Future APIs/evaluation must use these guarded services and must not cache text
across revocation. Direct database access is outside the application guard.

The existing five-second transaction bound, three-second statement timeout,
one-second lock timeout, ownership/consent checks and sanitized errors remain.
No automatic retry, transcript logging or external provider call is added.

### Verification and unfinished safeguards

Disposable PostgreSQL tests cover independent authorities/services and connection
pools, a new Python process with no inherited consent RAM, withdrawal before any
capture, duplicate withdrawal, rejected reads/new writes/duplicate-event reads,
session creation after withdrawal, both possible write/withdrawal lock orders,
failed metadata cleanup, explicit cleanup retry and unrelated-interview isolation.
Migration tests exercise upgrade/downgrade/re-upgrade on a disposable schema and
verify a single linear head. Existing consent and graceful-caption regressions
are included. No real candidate data or live recognition is used.

Verified on 16 October 2026: the combined backend regression run passed 120
tests; one subsequently added unauthorized-withdrawal PostgreSQL test also passed
(121 tests across the two runs, none skipped). The test readiness probe now waits
for PostgreSQL's final TCP listener instead of its temporary initialization
server. Disposable containers were removed afterward. Python compilation and
`git diff --check` passed. No frontend files changed, so TypeScript/build checks
were not required for this backend-only increment.

**Still not implemented:** verified physical deletion, deletion retry/reconciliation
workflow, maximum 30-day retention enforcement, authorization for withdrawal after
the existing join window closes, cross-process pending-consent negotiation,
post-interview finalization policy and live transcript-writing integration.
Existing join-window checks were not bypassed. Deletion and retention must be
finished before storage activation. Database marker enforcement here does not
claim a completed transcript, deletion or production readiness. No demo migration,
LiveKit/Whisper/caption change or runtime activation occurred.

## Historical Increment 2A: internal consent integration at bab21e8

Based on graceful-finalization commit `7a4fd57`, in the independent
`feature/f4-transcript-consent` worktree. No original F4 runtime or database
is changed. `TranscriptConsentCoordinator` is an internal service integration,
not an HTTP API. It is not instantiated by app startup; there is no enabled UI
storage control, caption hook or call to `append_final` in this integration.

### Approved disclosure

The owner approved the following wording on 16 October 2026. The exact text is
versioned as `optional-transcript-storage-v1` in `transcript_consent.py`:

> **Optional Interview Transcript Storage Consent**
>
> I agree to the storage of a text transcript of this interview for review by the authorized recruiter.
>
> I understand that:
> - Both participants must independently consent before transcript storage begins.
> - Declining consent will not prevent temporary live captions.
> - This consent does not authorize audio or video recording.
> - Stored transcripts will be retained for no more than 30 days after the interview, unless deleted earlier.
> - Either participant may withdraw consent and request deletion of the stored transcript.
> - AI-assisted evaluation and any disclosure to external AI providers will require separate, clear information about how the transcript is used.
>
> I understand that speech-to-text transcription may contain errors.
>
> **I agree to optional transcript storage.**

This approval defines policy; it does not prove enforcement. The existing live
caption consent and no-recording/no-saved-transcript UI remain unchanged.

### Implemented execution and trust boundary

1. A future authenticated adapter calls `prepare` using the actual request,
   interview ID and, for recruiters only, owned job ID. The existing authority
   authenticates the recruiter cookie or independent candidate invitation cookie,
   enforces mutation protection, ownership/current criteria and the join window.
   The coordinator allocates one server-generated capture UUID and returns the
   disclosure/version. Preparing alone does not constitute agreement.
2. Each participant separately calls `decide(..., decision='accept')` with that
   capture ID and `X-TalentTrace-Storage-Consent: optional-transcript-storage-v1`.
   Role/actor/owner come from authentication, never client role fields. The
   recruiter cannot supply the candidate's consent. HMAC receipts remain private
   in RAM; no endpoint accepts serialized receipts.
3. Once both receipts verify, `create_session` reuses its existing five-minute
   expiry, HMAC binding, candidate-invitation revalidation, current criteria and
   database locking/identity checks. It creates only `active/pending` session
   metadata on a database with migration 0010, never transcript turns. The
   coordinator reports `authorized_session_no_transcript`, with
   `transcript_saved=false` and `transcript_writing_enabled=false`.
4. Duplicate acceptance reauthenticates and reuses the original receipt and
   timestamp; existing session creation remains idempotent. Expired receipts
   fail closed rather than silently renewing agreement. Restart/recovery or
   explicit fresh-consent lifecycle is future work. Unknown captures, changed
   actors, wrong interviews, incorrect versions and malformed receipts fail.

The coordinator retains at most 100 interview entries and does not evict or reset
revoked entries. One process lock serializes consent, session creation and
withdrawal. This is intentionally a bounded prototype, not multi-worker
coordination. There is no automatic retry. Lost commit acknowledgement remains
uncertain; metadata might exist even when creation did not return successfully.

### Withdrawal: implemented limits and required durable safeguards

The approved rule is interview-wide revocation by either participant: block
future/in-flight writes, discard unsaved storage text, immediately hide already
stored text from recruiters/APIs/evaluation, then use authorized retryable
deletion and verify completion. Maximum retention is 30 days after the interview,
with earlier deletion on withdrawal. These rules must precede real storage.

Implemented here: authenticated `decline` or `withdraw` closes the process-local
authorization fence, clears both receipts and invalidates them in this authority.
No new acceptance or capture reset can restore it. If session metadata may exist,
the coordinator requests interrupted/failed closure through `finish_session`;
it never calls this saved/completed or deleted. Cleanup failure retains a pending
flag, and a caller may explicitly retry closure. Revocation stays in place even
if that database operation fails. No storage text is buffered by this service.
There is no dependency on temporary captions, which may continue normally.

**Not implemented/enforced durably:** revocation survives neither process restart
nor another worker. Existing internal `append_final`/`list_turns` are foundation
methods, not protected by this coordinator lock, and must not be exposed or
connected to live recognition yet. They do not provide the approved durable
withdrawal, immediate read suppression, verified deletion or 30-day expiry.
Responses explicitly report `durable_revocation_enforced=false` and
`deletion_verified=false`; an empty capture is not proof of a deletion workflow.

Recommended activation prerequisite: a reviewed later migration for durable
interview-wide revocation/deletion state, transactional checks that serialize
every write with withdrawal, access checks for all reads/evaluation, bounded
retention enforcement, authorized retryable deletion with verification and
crash/uncertain-commit reconciliation. No competing 0011 revision is created.
Any necessary database changes require a separate increment and approval.

All current consent actions retain the join-window check. After-window withdrawal
authorization and trusted post-interview finalization need separately designed
paths; do not bypass the window in the existing consent/session creation logic.
No policy enforcement, deletion completion or production readiness is claimed.

### Validation and remaining increment

Synthetic unit tests cover missing/declined consent, independent roles,
duplicates, wrong capture/interview/version, expired/tampered receipts,
unauthorized access, process-local withdrawal/creation races, cleanup failure,
uncertain commits, bounded state and absence of routes/writers. Disposable
PostgreSQL tests exercise actual cookie authentication, metadata-only creation,
duplicate creation, withdrawal closure, impersonation and closed join windows.
Existing caption/normal-stop tests remain regression checks. No frontend file
changes require TypeScript checks in this increment.

Verified on 16 October 2026: 112 backend tests passed across the transcript
foundation, consent coordinator, caption finalization, captions, interview
access and LiveKit service suites. Real PostgreSQL tests used the existing
disposable-container convention on loopback port 54402 and removed that
container afterward. No demo migration or runtime activation occurred. Python
compilation and `git diff --check` passed. No physical-device consent UI was
tested because this increment deliberately exposes none.

Increment 2B (not started) is trusted finalized-turn integration, gated on the
durable safeguards above and a reviewed activation plan. Raw audio storage and
external AI evaluation are not authorized by this disclosure.

## Historical Increment 1 foundation (still inactive)

## Implemented, inactive foundation

Migration `0010_interview_transcripts` follows `0009_bulk_scheduling`. It adds
capture sessions anchored to `InterviewSchedule.id` and immutable final turns.
It is tested only on disposable PostgreSQL; applying it to the F4 demo needs
separate approval. No caption writer, route, UI, worker or SMTP change enables it.

Session lifecycle: `active/pending` on creation; `active/saved` once a turn commits;
`completed/saved` on clean completion (including legitimate silence). Interrupted
or failed persistence becomes `partial` when some turns exist, otherwise `failed`.
A completely unavailable database cannot record its own failure; the caller must
retain/report the sanitized error and reconcile later. In-flight sessions left
active after a crash require later explicit reconciliation, not automatic success.

Both parent foreign keys use RESTRICT. Neither interview deletion nor capture
deletion silently removes transcript text. No retention period, purge job or
deletion endpoint exists; final retention/deletion/withdrawal policy is unresolved.

## Trust boundary

`StorageConsentAuthority.accept()` verifies the existing recruiter session and
owned interview, or the candidate invitation session, plus the join window. It
requires an explicit POST storage-consent version header distinct from temporary
caption consent. A server clock supplies acceptance timestamps. Its opaque HMAC
receipt binds authenticated actor/role, interview, capture UUID and wording
version, and is valid for five minutes for session creation. Receipt validity is
not a transcript retention rule. Dictionaries, booleans, altered receipts and
receipts from another authority/capture cannot create a session.

No current route calls this method. Authentication alone must never invoke it.
Future integration must show separately approved storage wording and require
each participant's explicit action. The version used in tests is synthetic;
production consent wording and policy are not established by this foundation.

The service is internal trusted application code, not a client-facing ingestion
API. `FinalTranscriptEvent` rejects intermediate events, invalid roles/timing,
blank/oversized/control-character text and extra fields. The final marker does
not cryptographically prove ASR provenance: only the future trusted recognition
adapter may construct events. Do not expose this service as a client text-write
endpoint or take an owner UUID from an untrusted request.

## Transactions and identities

Session creation serializes on the existing interview. One active capture per
interview is enforced by a partial unique index. Reconnect requires a new capture
UUID and fresh receipts; close/reconcile the preceding session first.

Every turn has a stable UUID and a unique `(session_id, sequence)` key. Repeating
exactly the same event returns the existing row; mismatched identity/payload is a
conflict. Identical speech with different event identities remains separate.
Writes/finalization lock the capture row, so concurrent speakers and duplicate
writes cooperate. Validity and ownership checks precede writes. Finalized sessions
reject new turns but allow reconciliation of an already-saved identical event.

Transactions have a five-second application bound, three-second statement timeout
and one-second lock timeout. Flush failures roll back and produce fixed errors;
lost commit acknowledgement is explicitly uncertain. There is no automatic retry,
queue or guarantee that RAM-only recognition results survive a process crash.
No transcript text is logged; callers must not log event models or SQL exceptions.

The internal `list_turns` read checks recruiter ownership and orders sessions by
server start/UUID, then turns by relative start/sequence/UUID. It permits bounded
offset pages for a fixed dataset; a later public API should use stable cursors
for concurrent append/retrieval. Historical reads do not require an open join
window or unchanged job revision. This is not an authenticated retrieval endpoint.

## Not implemented in this increment

Live consent issuance, storage-consent withdrawal, caption integration, cross-worker
coordination, crash reconciliation, transcript API/viewer, retention/deletion,
human review/corrections and F5 handoff. Persisted text must be treated as unverified
ASR, not approved hiring evidence. Raw audio/video is not stored. Existing live
caption consent and duration limits remain unchanged.
