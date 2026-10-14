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
- Each role has its own local model subprocess and four-second bounded chunks.
  One additional four-second chunk per role may wait in RAM during inference; larger
  backlogs stop captions. Native inference is terminated on stop instead of leaving a CPU thread running.
  Missing model/package fails closed. Slow inference exceeding buffer capacity
  stops rather than accumulating a whole interview or pretending nothing was lost.
- Maximum 120 seconds, 120 caption events, one interview per FastAPI worker,
  two role sockets; waiting for consent is also capped at 120 seconds. Authorization
  is rechecked each second. This is an isolated single-worker proof, not a distributed
  production consent system. Fresh connections/consent are required after stopping.
- Captions are short final chunk results, not native streaming/interim Whisper
  output. Relative timestamps represent chunk receipt timing, not precise word
  alignment. Chunk boundaries can cut words; limited synthetic measurements are below.
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

## Physical-microphone diagnosis — 13 Oct 2026

**User-observed:** real Edge microphone captions appeared, including inaccuracies
and duplicated phrases. This does not establish independent microphones or
cross-network verification. Speaker labels identify authenticated capture streams,
not diarization: two sessions capturing the same microphone can label the same
words under both roles. No automatic deduplication or provider change is justified.

**Confirmed by safe runtime metrics:** four physical runs stopped after 4.38,
14.23, 16.41 and 12.17 seconds, all on bounded PCM-buffer overflow, not the
120-second cap. The latest run had 120 recruiter and 121 candidate 100-ms frames.
The browser frame counter resets for each new caption AudioContext; 121 represents
approximately 12.1 seconds, not the full two-minute allowance. Nonzero PCM and
completed/nonempty decoding and caption delivery were observed for both roles.
Incoming RMS maxima were 0.261163/0.278254; RMS alone does not prove good speech
quality or recognition accuracy. Inference still active at overflow exceeded two
seconds (latest approximately 2.11 seconds); no speech content was logged.

The server initiated the overload stop and the browser then closed its dedicated
caption AudioContext. The LiveKit microphone remaining live/enabled is intentional
so the interview can continue. Thus closed caption context was a shutdown result,
not evidence that physical microphone capture caused this stop. Decode errors
after worker termination are not proof of malformed microphone PCM. The exact
contributors to slower physical recognition (speech/noise, shared microphone,
CPU contention) require further controlled measurement.

**UI correction:** report Live only after AudioContext resume succeeds and its
state is running; handle unexpected closed context or ended source track; detach
listeners on cleanup; suppress late startup/error callbacks from an obsolete
session. Normal shutdown explicitly separates captions from the still-live
interview microphone/video. Consent, bounded buffers, overload handling, local
provider and two-minute limit remain unchanged. Four production-handler regression
tests cover early closure, pending-start cleanup, normal server stop, non-running
resume and ended tracks. Frontend: 134 tests, type check and build passed.

**Remaining limitation:** physical two-speaker sustained transcription is not
verified. Repeat a short English test with headphones, one speaking microphone
at a time and the other muted, then compare with separate physical devices. Stop
on overload; do not silently discard audio or claim missing speech was recognized.

## Bounded reliability correction and controlled check — 13 Oct 2026

**Measured:** latest physical input remained approximately 10–11 100-ms frames
per second. Speaking-role inference often took 1.3–2.0 seconds and was still
active after 2.25 seconds at a 32.34-second overflow. Muted-role decoding was
mostly inexpensive silence, but zero-valued frames were still forwarded. This
explains the immediate overload mechanism versus the faster synthetic input;
the contribution of noise, overlapping microphones and speech complexity inside
the model remains unconfirmed. Do not infer those causes from RMS alone.

**Implemented:** allow two pending two-second chunks per role, capped at 128,000
bytes (four seconds), plus the active 64,000-byte chunk. Decode exact two-second
chunks in order without discarding speech or growing the queue. Timestamp metadata
retains bounded frame-receipt timing during queueing and muted gaps. Persistent
overload still stops safely. The original 120-second cap remains unchanged.

The interview mute now gates the separate browser-to-STT path explicitly, including
disabled or device-muted tracks. Heartbeats, consent and the peer stream remain
active. Pending pre-mute audio is retained; no pause is hidden as fresh speech.
This is not a complete gap-event or reconnect protocol.

**Controlled verification:** real FastAPI/WebSocket/LiveKit/local CPU Whisper with
varied, longer in-memory synthetic English speech. At 45.3 seconds both roles were
active, 43 caption results had been produced and no overflow occurred. Operator
withdrawal was received at 56.16 seconds, rather than exactly 45 seconds. Inference
mean/max was 929/1391 ms (recruiter) and 935/1390 ms (candidate); maximum measured
pending audio was 1.9 seconds. Both roles completed 27 chunk decodes, all nonempty.
No accuracy claim is made for those generated results. Worker RAM peaked at
480.4 MiB; mean CPU approximately 176% and sampled peak 390% of one logical core
(approximately 22%/49% of eight logical cores). Sampling is approximate.

A separate brief real mute check observed recruiter/candidate frame deltas 20/0
over two seconds; after unmute, 21/20. Withdrawal stopped captions without ending
the video interview. Local model and provider were unchanged; no cloud STT call,
recording, stored transcript or audio download was used.

**Still unverified:** sustained two-minute physical speech, reliable recognition
accuracy, and full-interview transcription. The four-second queue absorbs transient
delays; it cannot make a persistently slower-than-real-time CPU keep up.
See the full-interview recommendations in `f4_streaming_stt_plan.md`.

## Four-second batching and cross-device diagnosis — 13 Oct 2026

**Confirmed latest physical stop:** 40.20 seconds, `audio_buffer_overflow`, with
401 received 100-ms frames per role. No transport failure was recorded. Several
completed physical decodes exceeded two seconds, and the four-second pending
reserve filled. Non-silent physical speech can cost more than the short synthetic
fixtures; actual noise/overlap/recognition-complexity contributions were not proved.
Historical CPU utilization for this physical session was not captured.

**Measured local batching comparison:** concurrent two-role decoding, same local
CPU/int8 model, six varied synthetic offsets per role. Two-second batches averaged
940 ms (max 1109), real-time factor 0.47. Four-second batches averaged 961 ms
(max 1094), real-time factor 0.24. The comparable call cost supports amortizing
per-call inference overhead rather than extending the queue again. This is
synthetic evidence, not a replay or recording of personal speech.

**Implemented correction:** four-second chunks (128,000 bytes of 16-kHz mono PCM16)
with the pending limit unchanged at four seconds per role. Parent/worker framing
and service batching share the same bound. One active plus one pending chunk
remains bounded; no audio is silently removed to keep up. Two-party consent, mute,
withdrawal, overload failure and the 120-second cap remain unchanged. Source
receipt timestamps are preserved.

**Controlled actual API/WebSocket/local-provider check:** 30.27 seconds through
the existing Vite WebSocket proxy, authenticated recruiter/candidate sessions,
explicit two-party consent and varied synthetic PCM. 274 frames per role sent
and received; six nonempty captions per role delivered to both sockets. No
unstated overload/transport stop. Operator withdrawal ended processing at
30.28 seconds; the final 3.4 seconds per role were not decoded and were cancelled
as required by withdrawal. This was not a browser-capture, physical-device,
LiveKit-media or cross-network test. Mean decode time 938/924 ms; after-chunk-end
API delivery mean/max 0.931/1.188 seconds. Worker RAM peak 476 MiB.

**Trade-off:** final captions now wait for a four-second batch before inference;
first-sample latency can therefore be approximately five seconds in this synthetic
check. This does not establish accuracy or meet an approved interactive latency
SLA. Earlier full-interview latency proposals require review. Real physical
120-second reliability remains unverified; request owner participation before
another full physical test. A persistently slower-than-real-time decoder can
still exhaust the fixed pending bound.

**Cross-device recommendation only:** invitation URLs use the recruiter page's
origin. A link made on 127.0.0.1/localhost points back to the receiving device,
not the office laptop. Additionally, a consumed single-use invitation cannot
be moved to another browser; issue a fresh link from the reachable test origin.
Join windows, expiry, revocation and consent still apply.

Use one LAN-only trusted HTTPS origin on the same private network, with a free
local reverse proxy such as Caddy. Keep frontend/backend bound to loopback;
proxy the UI and `/api` (including WebSockets) through that single origin. Trust
the local test CA explicitly on both devices; do not bypass certificate warnings.
Restrict the listener/firewall to authorized test devices, allow only the exact
HTTPS Origin/Host, and enforce Secure/HttpOnly/SameSite cookies while retaining
the candidate cookie path. Current development cookies omit Secure, so this
must be addressed in an approved isolated TLS configuration before testing.
Do not disable security checks or expose development services publicly.

No proxy, certificates, tunneling tool, network/firewall changes or deployment
were performed. Installation, certificate trust, listener/firewall configuration
and the two-device live test all require explicit approval.

References: [MDN secure microphone/camera contexts](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[Caddy local automatic HTTPS](https://caddyserver.com/docs/automatic-https),
[Caddy WebSocket reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).


### Offline bounded pause segmentation evaluation - 13 October 2026

Documented experiment, NOT deployed: an outside-Git prototype uses 100 ms frames,
a 200 ms low-RMS pause after two seconds, and a strict four-second maximum.
All samples and timestamp spans are preserved, including silence. No overlap,
speech dropping, larger pending buffer, model download or cloud call was added.
Offline EOF flushes a partial tail once; withdrawal cancels it and rejects later
input. This is not an implemented live flush policy.

Twelve fixed English sentences were synthesized offline at Windows TTS rates
-2, 0 and +2. Identical audio was decoded by tiny.en/int8/greedy with two concurrent
workers. Audio and recognized text stayed in RAM; only aggregate metrics persisted.

| Rate | Fixed WER | Pause WER | Technical terms fixed/pause | Calls per role fixed/pause |
| --- | --- | --- | --- | --- |
| Slow | 30.70% | 18.42% | 6/11 / 9/11 | 19 / 24 |
| Default | 14.91% | 15.79% | 9/11 / 9/11 | 16 / 18 |
| Fast | 14.91% | 12.28% | 8/11 / 9/11 | 12 / 13 |

Pause-aware mean decode: 0.74-0.83 seconds; maximum: 0.953 seconds. Two-worker
wall-time/audio-duration ratios: 0.215-0.248. Peak benchmark RAM: 413.4 MiB;
CPU: 443.8% of one core (about 55.5% of eight). Offline first-sample latency
estimate: 3.80-4.39 seconds, versus fixed 4.57-4.90 seconds, excluding browser,
network and live queue scheduling. These do not prove physical-microphone accuracy.

Eight prototype tests passed: continuous/fast input, silence, mixed waveforms,
sample/timestamp conservation, pause boundaries, short tails, mute timestamp gaps,
withdrawal rejection and a two-role delayed-worker queue simulation. Three-second
simulated decoding stayed bounded; five-second decoding explicitly overflowed the
unchanged four-second pending capacity. No production/browser test was performed.

Recommended: retain deployed fixed four-second decoding. The prototype has mixed
accuracy and more calls. Next evaluate bounded look-back boundary selection offline
using the same model, without overlap, speech dropping or added pending capacity.
Continuous speech must still use the maximum. Real noise and overlapping speakers
remain unverified; the mixed-waveform test only proves sample conservation.


### Implemented bounded extended-duration test - 13 October 2026

Decision: retain tiny.en/int8/greedy and fixed four-second batching. Pause-aware
segmentation remains an offline experiment, not approved for live integration.

Implemented, automated-test verified only: LOCAL_CAPTION_TEST_DURATION_SECONDS
has a 120-second default and accepts 120-300 seconds. A value above 120 requires
ENVIRONMENT=development and LIVEKIT_SYNTHETIC_DEMO_ENABLED=true. It is server
configuration, not a client request option. Use 300 only in an approved isolated
runtime; the flag does not itself prove database/network isolation. No existing
runtime settings were changed and no five-minute live test has been performed.

Session processing ends at the earlier of the configured duration and the existing
interview join-window expiry (scheduled duration plus the existing 15-minute grace).
Candidate invitation expiry can shorten the shared caption session further.
Audio ingestion and post-decode publication check this deadline; the existing
one-second authorization watcher additionally stops access after revocation or
ownership changes, including while muted. Consent withdrawal/disconnection closes
workers, clears pending audio/captions and suppresses late results. Reconnection
requires both new consents and cannot bypass an expired authorization window.
This does not remotely disconnect already connected LiveKit participants.

The server active event reports duration_seconds. Frontend caption validation and
status respect that limit, up to 300 seconds and 150 events, retaining only 30
visible captions. Consent copy discloses the possible isolated five-minute test.
Four-second active and four-second pending audio bounds per role remain unchanged;
no transcript storage, model change, retries or speech dropping was introduced.
An incomplete tail is canceled at termination, not claimed as transcribed.

Risks: longer sessions increase exposure to slow/noisy decoding, CPU contention and
provider/process failures. Previous synthetic two-worker measurements used about
0.4-0.5 GiB worker/benchmark RAM and up to about 55% of eight logical CPUs; these
are not five-minute resource guarantees. Physical four-second decode maxima reached
about 3.19 seconds. Queues stay bounded and still fail explicitly on overload.
First-sample caption latency remains roughly four seconds accumulation plus decode.
Accuracy of natural physical speech remains limited and unverified by synthetic WER.

Next supervised check, requiring approval before restart/live execution: configure
only isolated backend 8011 to 300 seconds, verify matching frontend 5184 protocol,
prepare a fresh synthetic interview and unclaimed invitation, then collect numeric
per-role ingress, backlog, latency, CPU/RAM and stop-reason metrics for five minutes.
Check mute, both consents, cap, video independence and withdrawal in separate bounded
phases; do not claim both a full-cap and early-withdrawal pass from one session.
Preserve all databases and other demo services; restore the default after the test.


### Provisional model decision and requirements closure - 13 October 2026

Retain tiny.en/CPU/int8/greedy/fixed-four-second batching. The same accepted
75.3-second physical read-aloud input gave tiny/base script-based WER 35.09/33.33%,
approximate technical-term metric 3/4 out of 11, and mean decode 1.022/1.722 seconds.
Base's modest accuracy improvement does not justify a deployed model switch.
No speech was reprocessed. Captions remain unverified until reviewed.

See [F4 requirements review and inline architecture decision](f4_requirements_review.md)
for the synthetic/physical comparison, normalization/reference/tail bias, available
architecture evidence, missing official BID/WBS/clarifications, and the proposed
transient review increment. Full-interview duration, transcript review/persistence
and F5 integration are not completed by this proof.

Only the comparison harness on 5185/8012 was stopped. Isolated F4 5184/8011 remains
untouched with effective 120-second default. Audited harness paths have no saved
microphone audio or decoded transcript artifacts; logs are empty and saved results
contain aggregate metrics only. This is a scoped code/filesystem review, not a
forensic guarantee about operating-system/browser memory or swap.

## Fresh-session saved-score restoration (14 October 2026)

Implemented: Candidate Screening â†’ selected owned confirmed job â†’ Load saved scores.
A read-only GET /api/v1/jobs/{job_id}/scores discovers up to 20 current-version/current-
revision batches and reuses load_scores validation. Foreign jobs return 404; unconfirmed,
changing jobs or excess batches return 409. No parsing/model call or schema change.
The UI reuses ScoreDetails and InterviewScheduling; only eligible results are selectable.
Eligible unscored selection retains the existing explicit uncertainty acknowledgment.
Job/revision changes clear selection and suppress stale responses. Raw screening results
are not reconstructed from score rows. Saved explanations/source references are shown.

Verified: 140 frontend tests, type checking/build and 26 focused backend score/interview
regressions passed. Authenticated browser loaded persisted scores, disabled excluded
selection, selected an unscheduled eligible synthetic candidate, and saved one 30-minute
Asia/Dhaka interview for 14 October 15:37 (09:37 UTC). Interview page opened and invitation
creation exposed its copy control without disclosing the bearer link in logs. No Groq
call/upload occurred. Physical join, media and captions are pending owner-operated checks.
Backend 8011 restarted using the existing isolated diagnostic launcher, retaining data
and 120-second tiny.en configuration. Intake and other demonstrations remain unchanged.

## Candidate self-scheduling increment (synthetic demo rules)

Implemented: selected eligible saved candidate â†’ Generate scheduling invitation â†’
Copy scheduling link â†’ candidate opens /interview-schedule without recruiter login â†’
View available slots â†’ Book this interview â†’ private joining link. No email is sent.
The seven proposed weekday starts, Friday alternative starts, Asia/Dhaka and 60-minute
appointments are demo rules, not official BJIT policy. Availability covers today plus
13 days, omits past starts and overlaps, and is rechecked on booking.

Scheduling capabilities are independent of interview joining capabilities. Only SHA-256
hashes of 256-bit random tokens are stored; scheduling tokens expire in seven days.
Replacing a scheduling invitation revokes previous links for the same selection.
Job/batch/upload/recruiter/revision are bound server-side; candidate requests contain
only bearer and selected UTC start. Current saved eligibility and explicit approval
are rechecked. Unscored eligible selection requires recruiter acknowledgment.
Booking consumes the scheduling invitation atomically, creates the existing interview
record/screening snapshot, and creates a separate hashed one-use interview invitation.
The joining bearer is returned once, retained only in the candidate page's memory;
if delivery is uncertain or the page is lost, recruiter issues joining access through
existing controls. No automatic booking retry. Fragment tokens are removed from URLs.

Both manual and candidate scheduling lock the Recruiter row before job validation,
then check half-open time overlaps and write within the same transaction. In this
increment the recruiter is the interviewer/resource. Touching endpoints are allowed;
actual overlap returns 409. Existing candidate uniqueness remains a second safeguard.
No direct SQL/import path should insert interviews bypassing this guard. Scheduling
slots are advisory until reservation commits. Existing overlaps are not repaired.

Migration 0006_self_scheduling adds only scheduling_invitations. It was applied and
verified on disposable PostgreSQL schedule_test at loopback 54401, never the existing
F4 demo at 54378. Real PostgreSQL tests exercised candidate/candidate and candidate/manual
races (one success, one conflict), consumed-token rejection, and removal of booked slots.
Focused expiry/revocation/stale-selection, request protection and slot/overlap tests
passed; frontend tests cover unscored approval, fragment cleanup and protected requests.
Live candidate browser booking remains unverified until separately approved demo migration
and backend reload. Existing 5184/8011 and intake services were not restarted.

Not implemented: email delivery, calendar synchronization, rescheduling/cancellation,
multiple interviewer resources, configurable policy administration. Next: readiness
check/backup and explicit approval to migrate isolated F4 demo; then supervised booking.
Email needs an approved sender/recipient workflow and delivery/duplicate-send tracking.

## One-click synthetic scheduling/confirmation email

Implemented, disabled by default: select eligible saved candidate, enter an approved
synthetic recipient, then Send Scheduling Invitation. No persisted CV email exists in
score records; addresses are explicitly recruiter-supplied and backend-allowlisted.
Example-domain recipients are rejected. SMTP_SSL uses the standard library with
certificate validation, socket timeouts and no debug logging/retries. There is no
configured sender in this environment and no Gmail OAuth/Calendar integration.

Required ignored configuration: INTERVIEW_EMAIL_ENABLED (leave false until approval),
INTERVIEW_EMAIL_SENDER, INTERVIEW_EMAIL_RECIPIENTS (JSON list), INTERVIEW_PUBLIC_ORIGIN
(reachable HTTPS origin), INTERVIEW_SMTP_HOST, INTERVIEW_SMTP_PORT (default 465),
INTERVIEW_SMTP_USERNAME and INTERVIEW_SMTP_PASSWORD. Only isolated development with
synthetic-demo opt-in is allowed. Choose an approved dedicated sender and controlled
real test mailbox; never derive/send to fictional CV emails. No account or billing
setup occurs automatically. Credentials never enter frontend state.

Migration 0007_interview_email adds a private recipient binding to the scheduling
invitation and a token-free delivery ledger. One attempt per invitation/kind is unique.
A durable sending reservation commits before SMTP, so concurrent/repeated clicks reuse
known state rather than resend. Interrupted sending reads as uncertain. Accepted means
SMTP acceptance, not delivered/read. Failed, uncertain and not-configured are explicit;
there is no automatic retry or durable token/message spool. Manual replacement requires
review; replacing links can invalidate links in older messages.

Candidate booking commits its interview, consumed scheduling token, joining invitation
and confirmation attempt first. Confirmation then uses the SAME newly generated joining
bearer in memory and includes Asia/Dhaka date, start/end and duration. Mail failure does
not undo/duplicate booking; candidate sees email status plus Copy joining link. Lost or
uncertain response requires recruiter joining-access recovery; plaintext tokens are
never stored in delivery metadata. No automatic resending after uncertainty.

Only fake transport was exercised, including disposable PostgreSQL duplicate suppression
and confirmation timeout with preserved booking. Migration 0007 was tested on schedule_test
at 54401 only; existing F4 database 54378 and its services remain unmigrated/unchanged.
Real sending requires a readiness/backup/migration check, approved sender and allowlisted
recipient, reachable HTTPS origin and separate authorization for one test email.

Email increment verification: 31 affected backend tests passed before the final blank-
credential readiness regression; that guard is verified separately. 145 frontend tests,
production build/type checking, compilation and diff checks passed. Transport tests are
fake-only. SMTP accepted/uncertain delivery semantics and duplicate suppression were
verified on disposable PostgreSQL. No real messages or demo-schema changes occurred.
