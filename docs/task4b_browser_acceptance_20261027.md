# Task 4B — Offline browser F4 acceptance (27 October 2026)

## Result: PARTIAL

Implemented Task 4 was inspected at `8aa9c99928a6fbc5c706d00f589ee46603c736bb`.
This increment changes no production behavior. It validates the browser boundary
with real authenticated FastAPI routes and a fresh disposable PostgreSQL database
at `0017_booked_interview_email`. LiveKit and AssemblyAI were explicitly simulated.
It does not establish real browser-to-AssemblyAI acceptance or another F3 PASS.

## Observed browser evidence

- Independent Edge recruiter and Chrome candidate contexts authenticated through
  normal application routes. A fresh fictional job, eligible saved score, booking
  and invitation replaced the expired offline fixture; old evidence was preserved.
- The owner manually selected the approved role-specific WAVs. Generated tracks
  were used; no physical microphone/camera permission was requested.
- Both simulated media joins reached Connected. Remote participants remained zero:
  the LiveKit mock implements local generated tracks, not a two-party network.
- Optional storage consent was accepted independently before caption capture.
- Recruiter caption consent alone opened zero provider streams and accepted zero
  audio frames. Candidate consent opened exactly two simulated role streams.
- The actual browser AudioWorklet and authenticated WebSockets delivered nonzero
  PCM to FastAPI. A sample observation recorded 82 accepted frames per role,
  68/70 nonzero frames and eight finalized caption events per role. Recognition
  text was explicitly labelled simulated; no real ASR quality claim is made.
- Muting held recruiter accepted frames at 152 across two observations while
  candidate frames increased from 240 to 275. Unmute and normal finish were used.
- Finalization reported drained, with both simulated provider terminations
  acknowledged. Accepted/processed samples matched: recruiter 258304, candidate
  570624. These counts describe accepted audio, not full-interview completeness.
- The browser retrieved two saved role-attributed, timestamped turns. Persistence
  metadata reported interrupted/partial: three expected turns at the first storage
  failure, two acknowledged. Further caption publication continued. The UI honestly
  displayed incomplete storage. The precise first persistence error was not retained;
  do not infer a timing, database or provider root cause.
- After recruiter refresh/reopening, persisted privacy state reconciled. Candidate
  withdrawal displayed Deleted — verified; recruiter retrieval returned HTTP 409,
  and an independent database check found zero remaining transcript turns.
- Both roles left. Local video containers disappeared. A retained backend warning
  showed WebSocketDisconnect during final socket close; no resource leak was observed.

## Runtime and privacy boundaries

The incomplete host virtual environment was not modified. A test-owned Docker
backend overlay reused the complete existing local image with current backend
source. No package download was needed. The database used a dedicated internal
network; Docker Desktop required a separate test-owned ingress network for its
loopback published backend port. An in-process socket allowlist rejected external
transport; browser CSP restricted connections to the local test origin. Both
provider adapters were fake and only fake placeholder credentials were configured.

Observed external connections: **zero**; blocked external attempts: **zero**.
The test-owned frontend, backend and PostgreSQL were stopped; ports 5282/8042 were
released. Volumes, journals, configuration and earlier failed evidence remain.
Original Groq container identities/start times were unchanged; its application
continues separately on port 5280. No preserved database was migrated or modified.
Private artifact discovery remains in ignored `data/task4b-current.json`.
No credentials, invitation links, transcript text, raw PCM or private IDs enter Git.

## Verification and correction

- Backend focused suite: **17 passed**, zero failed/skipped after rerunning with
  the backend import path. An initial invocation from the repository root failed
  collection because `app` was absent from PYTHONPATH; no tests ran in that invocation.
- Frontend focused suites: **28 passed**, zero failed/skipped.
- TypeScript and production frontend build: **PASS**. Existing large-chunk advisory
  remains; no dependency or bundle-policy change was made.
- `git diff --check`: PASS.
- A timing-only test correction replaces a fixed 40 ms sleep with a bounded wait
  for the actual finishing event. This preserves the production 90-second guard
  while avoiding a Windows scheduler-speed assumption.

## Remaining live acceptance boundary

**Not ready for an unqualified external browser acceptance claim.** First obtain
an allowlisted persistence-error category in an isolated offline harness and
resolve/reproduce the partial-storage result, with a focused regression if a
production defect is confirmed. Do not retry a consumed invitation or process-local
provider attempt. The socket-close warning should also be checked during cleanup.

After offline readiness, a separately approved fresh trial must verify real
LiveKit transport plus real AssemblyAI recognition through these browser streams.
Recheck current AssemblyAI free credits/no paid billing and LiveKit Build allowance;
use fresh fictional access, independent storage/caption consents, bounded capture
and no automatic retry. Task 4's earlier real API recognition/persistence evidence
and historical F3 success remain separate from this mocked browser evidence.
