# Interview transcript persistence — Increment 1

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
