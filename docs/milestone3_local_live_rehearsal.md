# Local generated-speech browser rehearsal

Implemented: separate loopback-only services and a disposable database; no
transcript turns are preseeded by this launcher. Saved candidate eligibility is
explicitly an offline synthetic fixture, not a claim of live CV screening. The
launcher creates its interview through the existing authenticated scheduling API
and generates its separate one-use candidate invitation through the normal API.

## Local dependencies

Use the project's existing Python environment and installed frontend dependencies.
The existing PostgreSQL image must be cached and Docker running. The launcher uses
a new disposable container bound only to `127.0.0.1:54402`; it never connects to
54378/54379. It applies and exercises migrations through 0014 in that container.

The official [LiveKit local setup](https://docs.livekit.io/transport/self-hosting/local/)
supports `--dev`. This sprint downloaded the official GitHub Windows amd64 release
v1.13.10. Its ZIP SHA-256 matched the release asset digest:
`fd4b7c2c3c1e4c71adaa4f6a046ad1c0abaaaf1e09fae904b35bf231ffae11d2`.
Binary, ZIP, logs and configuration stay under ignored `data/livekit`.
No firewall rule, cloud room or public tunnel is required.

The following `data/livekit/loopback.yaml` restricts Windows RTC binding as well
as signaling. `--bind` alone was insufficient: the first attempted server bound
RTC interfaces broadly and was stopped before the corrected launch.

```yaml
port: 7880
bind_addresses:
  - 127.0.0.1
rtc:
  tcp_port: 0
  udp_port: 7882
  use_external_ip: false
  enable_loopback_candidate: true
  interfaces:
    includes:
      - Loopback Pseudo-Interface 1
  stun_servers: []
```

From this worktree root, run the official binary:

```powershell
& '.\data\livekit\livekit-server.exe' --dev --config data/livekit/loopback.yaml --node-ip 127.0.0.1
```

Verify TCP 7880 and UDP 7882 bind **only** to 127.0.0.1; port 7881 must not be
listening. The backend requires an explicit development opt-in and accepts only
`ws://127.0.0.1:7880`. The development frontend accepts it only from a 127.0.0.1
page; production builds retain the existing LiveKit Cloud URL restriction.

## Disposable backend and frontend

From `backend`, substituting your existing private provider file and local model:

```powershell
& 'D:\TalentTrace-F4-Local-20261012\.venv\Scripts\python.exe' tests/run_milestone3_live.py --env-file 'D:\VS Code\TalentTrace-AI\.env' --whisper-model 'D:\TalentTrace-F4-Local-20261012\models\tiny.en' --confirm-free-tier-synthetic
```

It reads only GROQ_API_KEY and LLM_MODEL from that file, disables email, uses the
normal consent runtime and enables privacy-bound durable analysis for its single
fictional job. It does not seed transcript text or call a model on startup.
Backend: 8022, default lifetime 1800 seconds. For a paced manual rehearsal add
`--max-runtime-seconds 7200 --interview-duration-minutes 120`. Maximum lifetime is
two hours, must fit the supported interview duration, and is printed at startup.
Invitation expiry is bounded by the matching interview/join window, not one hour.
This does not extend the two-minute caption-processing limit.
Ctrl+C/deadline removes its own
disposable database. The launcher does not start/stop unrelated services.

In a separate `frontend` terminal:

```powershell
$env:VITE_API_BASE_URL=''
node node_modules/vite/bin/vite.js --config vite.milestone3.config.ts
```

The 5190 proxy keeps API/caption WebSocket cookies same-origin with backend 8022.
Private login and candidate invitation are in ignored `data/milestone3/LOGIN.txt`
and `LIVE-TARGETS.json`. Do not paste those values into documentation or chat.

## Actual browser path to verify

1. Sign in at 5190 with the disposable login; open Interview Scheduling, select
   the synthetic Python job and Open interview. The saved booking is joinable.
2. In an independent browser context, privately open candidate_url from the
   targets file; accept its one-use invitation. Recruiter login is not a candidate
   capability. Never reuse an invitation after a different browser claims it.
3. Keep generated synthetic media checked on both pages. Select a short locally
   generated fictional WAV for each role **before joining**. The development
   selector decodes it in browser memory, with no upload or physical microphone.
   For example: recruiter asks "In Python, are lists mutable?"; candidate answers
   "Python lists are mutable. You can append new items." These files are generated
   fixtures, not recordings. Both must be at most 30 seconds / 2 MB.
4. Confirm synthetic test and join both participants. Independently accept the
   unchanged optional text-storage disclosure on each page, then independently
   consent to temporary live captions. No participant consents for the other.
5. After caption readiness, click Play generated synthetic speech on recruiter,
   then candidate. The AudioBuffer source feeds the published LiveKit microphone
   track; the existing AudioWorklet reads that actual track into the authenticated
   caption WebSocket and local Faster-Whisper. Do not inject PCM through an API.
6. Observe real caption text and speaker labels. Stop captions / Leave normally,
   wait for graceful finalization, check saved status and load timestamped turns.
   Failed/partial storage is not a complete analysis input.
7. Review the separate fictional-only Groq disclosure and explicitly Analyze
   finalized interview once. Follow the same operation status after uncertainty.
   Verify graph Q&A, reference quotations, four advisory dimensions and source
   turns. No numeric hiring score is produced.
8. Withdraw storage consent. Verify denied transcript/analysis retrieval and
   Deleted — verified, including derived rows. Stop owned temporary services.

At the current checkpoint, actual loopback password login, owned job/interview
loading, normal scheduling/invitation API creation and exact network bindings
have passed. The owner signed in through the actual built-in browser and opened
the saved job/interview. Generated recruiter WAV selection succeeded. The first
LiveKit connection failed before media publication; after fixing a diagnostic
race, the safe UI reports `livekit_connection (ServerUnreachable)`. The server
accepted signaling but the client closed before an RTC connection. This does not
yet establish whether the cause is browser-specific. An independent Edge check
is pending manual sign-in. No physical device or new model inference was used.

Full independent-browser media, newly recognized speech, finalization and live
durable Groq analysis remain **unverified**. Earlier seeded-input model/UI tests
are separate evidence. A disconnected event during initial connection previously
advanced the UI generation counter and hid the actual connection failure; the
initial connect catch now retains a fixed stage/allowlisted reason without
printing SDK messages, tokens or SDP. Unexpected post-join disconnect handling is
unchanged. A focused regression verifies that event ordering and secret redaction.

The owner subsequently verified Edge regular and InPrivate both joined with one
remote participant. Before storage consent, the 30-minute launcher deadline
removed the disposable backend/database at approximately 16:13 Asia/Dhaka.
Vite recorded consent-prepare ECONNREFUSED at 16:13:41 and candidate status
ECONNREFUSED at 16:13:46. The generic candidate "ended or revoked" message is not
proof of explicit revocation; any failed status check triggers that fail-closed
behavior. Those recorded prepare attempts did not reach the backend. Earlier
database state is unavailable after disposable cleanup; no consent is assumed.
Recovery uses a new disposable fixture and fresh authorization, never a consent
reset or timestamp edit. The old candidate link is unusable.
