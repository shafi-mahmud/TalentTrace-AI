# Task 4C — Receipt-bounded live transcript persistence

Date: 27 October 2026. Baseline: `4dd116e7c85c3e6f5bb0a0a00ece1bb72c261304`.
Branch: `feature/office-20261026-acceptance`.

## Result: offline browser persistence PASS

Real browser-generated PCM, AudioWorklet, authenticated FastAPI WebSockets and
fresh PostgreSQL schema `0017_booked_interview_email` were exercised. LiveKit and
AssemblyAI were simulated explicitly. No external provider connection occurred.
This is not live AssemblyAI browser acceptance or a repeat of F3 Cloud acceptance.

## First failure and evidence limits

Task 4B retained counters show at least 24 published captions (8 recruiter and
16 candidate) while its storage summary recorded two acknowledgements and three
expected turns when the adapter stopped attempting persistence. That expected
count is the failure boundary, not the total number of temporary captions. The
historical stored sequence identities and error category were not preserved before
verified withdrawal/deletion; they cannot honestly be reconstructed afterward.

Two fresh offline reproductions establish the defect:

1. A deterministic regression accepts both roles' first ten 100 ms frames normally,
   then delivers subsequent frames 10 ms early. Sequences 1 and 2 acknowledge;
   **sequence 3 fails with `invalid_recognition_time`** before the correction.
2. The existing authenticated API/PostgreSQL scenario, using Task 4B's immediate
   simulated recognizer and more aggressive first-frame arrival, rejects sequence
   1 with that same fixed category: eight emitted, zero saved, no completed capture.
   Sanitized diagnostics record only sequence/role/timing/outcome, never text or
   underlying exception details.

The first Task 4B error itself remains unrecorded; the confirmed reproducible code
cause must not be presented as a newly recovered historical log.

## Confirmed cause and correction

`LiveStreamingCaptions.audio()` previously placed each frame after the previous
frame's complete nominal duration. Its existing bounded jitter/burst admission can
accept frames slightly ahead of nominal pacing. Forcing nominal duration onto that
receipt timeline advances estimated recognition times into the future. The database
correctly rejects an end timestamp later than elapsed capture time. The storage
adapter then fences later writes; temporary captions can continue, correctly labelled
incomplete storage.

The correction stores each frame's observed receipt start/end bounds and interpolates
provider sample offsets inside those bounds. Estimates stay nonnegative, ordered and
no later than receipt. Muted gaps remain gaps. Admitted bursts can compress the estimated
interval; these remain receipt-based chunk estimates, not precise word-acquisition times.
PCM, sample counts and provider recognition content are unchanged.

Strict database time validation, ownership, consent, stable UUID/sequence identity,
transaction locking, duplicates, finalization and no-retry behavior remain unchanged.
No migration or timestamp tolerance was added. No missing turn was fabricated or replayed.

## Connected and browser acceptance

- Corrected immediate-provider/API reproduction: **8 emitted / 8 stored**, all
  acknowledgements, completed/saved, consistent authenticated reload and verified
  withdrawal/deletion.
- Fresh Edge recruiter and Chrome candidate: owner-selected role WAVs, generated
  tracks, separate optional storage consent before independent caption consents.
- Recruiter-only caption consent: zero provider streams, zero PCM, zero stored turns.
- Both consents: exactly two simulated streams; real AudioWorklets forwarded nonzero
  PCM separately. No physical-device permission was used.
- Both rendered caption lists contained **24** items. Normal finish reported drained,
  matching accepted/processed sample counts and two acknowledged simulated terminations.
- **24 expected / 24 acknowledged / 24 stored**, contiguous sequences 1–24. Every
  stored sequence, role, start and end exactly matched its trusted caption event after
  the storage capture offset. No persistence error was recorded.
- UI reported saved for accepted audio. After Leave, browser refresh, reopening and
  Load saved transcript, all **24** items remained visible. This does not establish
  full-interview completeness or real recognition accuracy.
- Candidate withdrawal: Deleted — verified; recruiter retrieval HTTP 409; direct
  identity-scoped SQL count zero. Both browsers had zero video elements after Leave.
- Negative tests retain incomplete/unconfirmed status after rejected or uncertain
  writes, with one write attempt and no automatic retry.

## Tests and safety

Final focused run: **23 backend passed** (21 unit cases, two authenticated disposable
PostgreSQL cases); **28 frontend passed**; zero failures/skips. Counts exclude earlier
repeated runs. The new jitter regression was observed failing before the fix, then
passing. API tests now also compare exact sequence sets, roles and capture-offset
mapping. TypeScript/production build and whitespace checks passed. The existing
large frontend-chunk advisory remains.

Only new test-owned PostgreSQL was migrated. The complete Docker dependency image
was reused with a small offline source overlay, fake credentials/connectors, a
local socket allowlist and local-only browser CSP. Private bounded diagnostics,
resource manifests and evidence remain ignored; locator: `data/task4c-current.json`.
The original Groq container identities/start times were independently unchanged.
Test-owned frontend/backend/PostgreSQL stopped; ports 5282/8042 released; volumes and
old evidence preserved. No paid/external calls, preserved database migration, merge
or push occurred. The earlier socket-close warning is separate from this timestamp
fix; normal test cleanup and resource release passed.

## Remaining live acceptance boundary

A separately approved, fresh, bounded browser trial must still combine real LiveKit
transport with actual AssemblyAI recognition and these browser streams. Recheck current
free allowances and billing protections, use new fictional access and independent
consents, and stop on first failure. No such external trial was started here. Historical
F3 and Task 4 real API evidence remain valid only within their recorded scopes.
