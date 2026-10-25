# Candidate access and concurrent interviews — 25 October 2026

Branch `feature/candidate-access-concurrency` starts at F11 finalization `e947bdc`,
preserving integrated analytics, publishing and the dismissal fix. No other branch
was merged or modified.

## Implemented candidate boundaries

`api/routers/interview_access.py` issues bounded single-use invitations and stores
only hashes of invitation and candidate-session credentials. Claim/revoke/rotation
uses the owned-job parent-lock convention; claim refreshes the invitation after
waiting so stale ORM state cannot reuse a claim. Cookies are HttpOnly, SameSite
Strict, path-scoped and Secure outside development. The initial bearer is captured
from the fragment and removed from browser history; it is not retained in storage.

Candidate grants resolve only the cookie's assigned interview, owner, current
criteria and join window. They do not accept a browser-selected role or room.
Replay, expiry, revocation, inactive recruiter and changed ownership/revision fail
closed. Recruiter-only review requires recruiter authentication, owned interview
and matching job. A candidate privacy/deletion receipt is not transcript-read access.

**Confirmed fix:** `frontend/src/api/livekitInterview.ts:candidateStatus` previously
accepted any HTTP 200 and waited without a deadline. It now requires exactly
`{status:'ready'}`, applies an 8-second abort deadline and sanitizes malformed JSON,
transport and HTTP errors without retries. The existing media lifecycle catches
failure, disconnects and clears media; its generation fence suppresses effects from
late responses. This is bounded polling, not instantaneous revocation: the check
interval is 15 seconds and browser scheduling/network delays still matter.

Ordinary Leave/disconnect intentionally retains the candidate session so the same
browser can reconnect within validity; this is not candidate logout. There is no
new explicit candidate sign-out/identity-verification feature. Owner revocation is
the terminal application-access control. Possessing an invitation/session does
not prove a person's identity. Separate browser profiles are required for distinct
candidate sessions: one profile has one cookie slot at this path. Cookies are
host-scoped, not port-isolated. No biometric or anti-cheating capability is claimed.

## Concurrent-interview support and exact limit

| Layer | Implemented / verified boundary | Remaining limit |
| --- | --- | --- |
| Media authorization | Locally signed real SDK grants use distinct HMAC room identities per interview and distinct participant slots per role/interview. No room-list/admin/data-publishing permission. | Actual simultaneous Cloud media not exercised here. Grants do not prove provider transport isolation by themselves. |
| Candidate sessions | Two separate synthetic browser clients claim separate invitations; revoking one leaves the other able to obtain its own scoped grant. Cross-owner revocation fails. | SQL transaction doubles, not a fresh PostgreSQL concurrency run. One candidate per browser profile. |
| F4 captions | Router safely rejects a second interview while one caption session occupies this backend process. Regression verifies the first remains untouched. | **Only one active caption room per process**, two role workers inside it. No multi-room or distributed transcription support added. |
| F11 | Delivery entries, run/epoch, consent, events and invalidation are interview-bound (maximum 32 bounded entries). Tests reject cross-run evidence and keep B authorized/suggesting after invalidating A. | Graph work is globally bounded/serialized; the real caption route remains single-room. This is not concurrent live F11 acceptance. |
| Transcripts | Persistence binds capture/turn records to interviews; review checks recruiter ownership and exact job before reading. New unit checks reject wrong-job and candidate-only review. | No new live PostgreSQL interleaving, retention/deletion race or concurrent Cloud storage trial. |
| Recruiter UI/booking | Existing UI has one active Room per component; independent sessions can coexist. | No multi-room supervision dashboard. Existing same-recruiter booking-overlap rules remain; no bypass introduced. |

An issued media JWT can outlive application-cookie revocation. Existing Cloud
removal uses scoped participant identity and a revocation cutoff, but this task
mocked that administrative boundary. Preserve the known self-hosted cached-JWT
revocation limitation. No guarantee of immediate provider disconnection or cached
token invalidation is established by these offline tests. No Cloud calls occurred.

## Verification

- Focused invitation, real SDK signing, captions, F11 delivery and bridge suites:
  **97 passed, 1 skipped** (43.99 s). Skip: explicit real local-Whisper model gate.
- Additional transcript-identity unit checks: **2 passed** (2.78 s).
  Total distinct backend passes **99**; one skip. These two cases use mocked
  identity/storage boundaries and do not imply actual database persistence testing.
- Full frontend: **312 passed**, zero failed/skipped. New status-poll regression
  checks exact success shape, abort signal, malformed HTML/JSON and sanitized errors.
- TypeScript and Vite build passed; existing >500kB LiveInterviewPage warning
  remains. Git whitespace checks passed.

No production backend change, schema/migration, model load, booking, real identity,
Cloud connection, external call, Docker operation, database reset or UI redesign.
No merge/push. Status: candidate controls implemented with explicit identity/media
revocation limits; end-to-end concurrent interviewing **PARTIAL**, multi-room F4
unsupported and safely rejected. Next acceptance needs separately approved isolated
resources, independent profiles and provider observations, not relaxed capacity.
