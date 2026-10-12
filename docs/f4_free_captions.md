# F4 increment 1 — free-only local caption foundation

## Provider and cost decision

**Implemented in code, live recognition unverified.** Cloud inference is not
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
  Native inference is terminated on stop instead of leaving a CPU thread running.
  Missing model/package fails closed. Slow inference exceeding buffer capacity
  stops rather than accumulating a whole interview or pretending nothing was lost.
- Maximum 120 seconds, 120 caption events, one interview per FastAPI worker,
  two role sockets; waiting for consent is also capped at 120 seconds. Authorization
  is rechecked each second. This is an isolated single-worker proof, not a distributed
  production consent system. Fresh connections/consent are required after stopping.
- Captions are short final chunk results, not native streaming/interim Whisper
  output. Relative timestamps represent chunk receipt timing, not precise word
  alignment. Two-second boundaries can cut words; accuracy/latency are unverified.
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

No real Whisper model, browser-media caption transport, account-level free credit
verification or cross-network proof has been performed. No real provider or
physical microphone was accessed for F4. Both running demonstrations remain on F3.

Before a live check, obtain owner approval for a separately provisioned local
environment, optional package/model download and the two-browser synthetic test.
Use a small approved English model directory outside Git. Set
`LOCAL_CAPTION_MODEL_PATH` only in the new isolated development runtime, with the
existing synthetic-demo gate enabled and matching trusted frontend Origin. Do not
modify the two preserved demos or provision models in their shared virtualenv.
Start/join with the existing F3 roles; each explicitly consents to captions. Verify
no audio before both agree, correct labels, stop/withdrawal from either role,
caption clearing, and usable A/V on caption failure. Do not enable any paid STT.

LiveKit Inference remains an alternative only after actual account credit and
no-charge limits are independently verified and the owner separately approves a
bounded live test. Google billing and Groq paid STT are not permitted fallbacks.
No permanent transcript tables, migrations, new agents or deployment are added.
