# F4 increment 1 â€” free-only local caption foundation

## Provider and cost decision

**Implemented; isolated synthetic local recognition verified on 12 Oct 2026.** Cloud inference is not
enabled. We have not verified the account's remaining Build credits or a hard
no-charge limit. Published allowances are not account-level evidence; no LiveKit,
Google or Groq STT request was made. No billing, payment or plan change occurred.
[LiveKit limits](https://docs.livekit.io/deploy/admin/quotas-and-limits/).

The chosen provider is local `faster-whisper` CPU/int8, loaded only from an explicit
pre-downloaded model directory, with `local_files_only=True` and offline flags.
There is no cloud fallback or automatic download. `requirements-stt.txt` is an
optional pinned installation, not an addition to normal backend dependencies.
It has not been installed in the existing demos. Local CPU/memory/electricity and
initial public package/model downloads still have resource costs, but there is
no metered STT service or payment account. Existing A/V Cloud usage is separate;
this proof adds no LiveKit subscriber/inference connection.
[Faster Whisper](https://github.com/SYSTRAN/faster-whisper).

## Implemented boundary

- React taps each browser's existing local LiveKit microphone track only after
  the server sends the two-party consent acknowledgement. No second microphone
  permission request, recording, MediaRecorder file or video capture is introduced.
- PCM16 mono 16-kHz frames flow through authenticated FastAPI WebSockets. Recruiter
  access reuses owned-schedule/session checks; candidate uses the current invitation
  session under its existing cookie path. Exact Origin checks, no query tokens,
  strict control strings, fixed 3,200-byte frames and message-rate limits apply.
  Roles are assigned server-side, never accepted from audio payloads.
- Both roles must opt in. One role alone cannot load/process audio in Whisper.
  Either role's withdrawal immediately stops its local tap and closes the server
  processing gate when received; no networked system guarantees zero transmission
  latency. Late recognition results are suppressed. Participant disconnect,
  authorization loss/revocation, timeout or failure stop the caption session.
- Each role has its own local model subprocess and two-second bounded chunks.
  One additional two-second chunk per role may wait in RAM during inference; larger
  backlogs stop captions. Native inference is terminated on stop instead of leaving a CPU thread running.
  Missing model/package fails closed. Slow inference exceeding buffer capacity
  stops rather than accumulating a whole interview or pretending nothing was lost.
- Maximum 120 seconds, 120 caption events, one interview per FastAPI worker,
  two role sockets; waiting for consent is also capped at 120 seconds. Authorization
  is rechecked each second. This is an isolated single-worker proof, not a distributed
  production consent system. Fresh connections/consent are required after stopping.
- Captions are short final chunk results, not native streaming/interim Whisper
  output. Relative timestamps represent chunk receipt timing, not precise word
  alignment. Two-second boundaries can cut words; limited synthetic measurements are below.
  Roles establish authenticated stream provenance, not verified speaker identity;
  malicious senders or acoustic cross-talk can contaminate audio. Headphones help.
- React keeps only 30 visible caption events in memory, renders escaped text and
  clears them on stop. No transcript/audio writes to PostgreSQL, disk, browser
  storage, LangGraph or logs. STT errors are fixed public states, without private
  exception bodies. Existing LiveKit video, microphone controls and leave continue
  independently. No copilot, ranking, scoring or hiring decision is introduced.

## Verification and remaining gates

Offline tests use synthetic PCM and fake recognition providers. They cover both
consents, premature audio rejection, separate role labels, bounded inputs/timing,
provider errors, late-result suppression, timeout, CPU overflow, secret-query and
foreign-Origin denial, unauthorized sockets and owned-child cancellation. Existing
interview, invitation, token and database-foundation tests remain regression checks.
Frontend tests cover strict caption events and the initially unconsented production
panel; they do not establish real microphone/AudioWorklet or recognition behavior.

### Isolated live verification — 12 Oct 2026

**Verified:** existing browser-to-backend microphone bridge (not a server-side
LiveKit RTC subscriber), real LiveKit synthetic A/V, authenticated WebSockets
through the Vite proxy, and local `tiny.en` CPU/int8 recognition. Model/packages
were installed only in an isolated environment outside Git; existing demos were
not changed. No paid/cloud STT calls or physical microphone capture occurred.

One participant's consent produced zero audio frames and no captions. With both
consents, real synthetic speech produced temporary recruiter/candidate captions.
Withdrawal by each role cleared both caption lists and stopped processing while
both LiveKit connections remained connected. This used two Edge tabs with distinct
role-cookie paths, not independent browser profiles or cross-network devices.

Initial direct inference measured approximately 0.5–1.1 seconds per two-second
chunk and 170 MiB per worker. Earlier short repeated browser speech samples had
mean word error rate 6.1%; this is not general interview accuracy. An observation
found eight captions within 10.66 seconds after activation, but did not measure
exact first-caption or end-to-end latency.

**Confirmed limitation:** live browser runs stopped on bounded input backlog,
including a 53-second run after allowing one pending chunk. The safety stop clears
captions and preserves the video interview; continuous two-minute browser
reliability is not established. CPU delay and browser delivery bursts need further
measurement before claiming real-time operation. No automatic retries were added.
The 120-second cap and delayed-result suppression remain covered by offline tests.
Physical capture, cross-network behavior and live provider-failure injection remain
unverified. Do not enable this proof in the preserved office demonstrations.

**Current checks:** 19 focused backend caption tests, 59 caption/interview/access
regression tests and 129 frontend tests pass;
TypeScript checking and production build pass (existing large-chunk warning).
The development proxy now explicitly forwards WebSockets. A five-second connection
acknowledgement deadline prevents indefinite connection-pending UI.

LiveKit Inference remains an alternative only after actual account credit and
no-charge limits are independently verified and the owner separately approves a
bounded live test. Google billing and Groq paid STT are not permitted fallbacks.
No permanent transcript tables, migrations, new agents or deployment are added.

## Reliability investigation — 12 Oct 2026

**Measured:** each browser supplied 3,200-byte PCM frames (100 ms at 16 kHz),
roughly 10 frames/second. A failed baseline ended at 75.24 seconds with the
recruiter pending buffer exceeding 64,000 bytes; completed inference averaged
785/793 ms per role. This identifies overload at the processing boundary, but
does not prove every earlier 53-second failure had the same underlying trigger.

Rotating the same synthetic speech across two-second cut boundaries reproduced
six default temperature decode attempts: 2.17–2.34 seconds versus ordinary
0.52–0.73 seconds with one CPU worker. The worker now requests `temperature=0.0`
for one greedy decoding attempt. This avoids hidden sampling fallbacks; it does
not guarantee recognition accuracy or real-time processing on every computer.

A subsequent two-role run ended at 28.67 seconds on the route task-count guard,
with only 625 ms of pending inference and PCM buffers below capacity. Candidate
frames included a zero-ms delivery gap (peak 12 frames/second). The route now
yields once after scheduling ingestion, so fast dispatch tasks can consume their
frames before the next task-count check. Task limits and bounded PCM storage
remain in place; no silence-discard policy or uncontrolled queue was introduced.

That run averaged 975/987 ms inference per role (maximum 1.28/1.33 seconds).
Two worker process trees peaked at 434 MiB and about 189% of one CPU core during
active resource sampling (approximately 24% of eight logical cores). These are
approximate local measurements, not a production hardware guarantee.

An intermediate unchanged-buffer run reached the cap at 120.03 seconds, with
115.0/107.4 seconds of delivered audio. This is not proof that 120 seconds of
speech were captured: browser audio clocks/production can differ from wall time,
and pending incomplete tail audio is cancelled at the cap. No audio was recorded
or transcript stored. No sustained-success claim is made for the final fix.

**Pending:** final two-minute real-browser verification after loading the route
fix. Automated execution approval rejected both isolated backend restart and
alternate-port service startup as blocked by policy. The existing 5183/8010
runtime therefore does not contain the final route change. Physical microphones
remain unapproved/unverified. Local changes must not be treated as live-verified
until a permitted isolated runtime passes continuity, cancellation and cap checks.

Metrics collected outside Git contain only bounded numeric timing, byte counts,
role labels, buffer sizes, decoder threshold categories and resource counters.
No raw PCM, captions, prompts, credentials or participant tokens are logged.
