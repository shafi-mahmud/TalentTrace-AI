# F4 streaming STT plan — 12 October 2026

**Recommended / Planned — not implemented.** No provider activation, dependency,
recording or transcript storage is added by this documentation.

**Free-only override:** the later owner instruction prohibits paid STT/overage.
The Google recommendation below is historical and is not authorization to enable
billing. Actual LiveKit account credits and a hard no-charge limit are unverified;
Cloud STT stays unused. The separately implemented, disabled-by-default local CPU
caption foundation is described in [Free-only captions](f4_free_captions.md).

## Current architecture

- `backend/app/api/routers/interviews.py` authorizes the recruiter; `interview_access.py`
  authorizes the candidate through invitation/session hashes and a join window.
- `backend/app/services/livekit_interview.py` derives opaque identities and signs
  scoped tokens. Human tokens cannot publish data; preserve that restriction.
- `frontend/src/components/LiveInterviewPage.tsx` is the shared media/control page;
  `CandidateInterview.ts` handles invitation acceptance. Camera permission and the
  synthetic-test checkbox are **not** transcription consent.
- Installed: server `livekit-api==1.2.1`, frontend `livekit-client==2.22.4`.
  Python RTC `livekit`, Agents, Google plugin and `google-cloud-speech` are absent.
  A signing SDK does not receive audio.
- System Design v2.1 page 1 documents Google streaming STT and participant streams;
  Workflow Design v1.1 page 1 supplies final STT turns to the later Co-Pilot.
  These remain planned. The older Meet/local-mic transport is not implemented;
  the proposal adapts the audio boundary to the working LiveKit interview.
- [F3 physical verification](interview_invitations.md) is user-observed local Edge
  testing, not an automated, cross-network or measured-latency result.

## Options and approval boundary

| Option | Dependencies / credentials | Decision |
| --- | --- | --- |
| **Direct Google streaming from a backend LiveKit subscriber** | Python `livekit` RTC + `google-cloud-speech`; existing LiveKit credentials; Google ADC/service identity, enabled Speech API and approved billing/project/region/model. | Recommended: genuine interim/final streaming without another agent framework or LLM. Small audio-pump/cancellation code is necessary. |
| LiveKit standalone Google STT plugin | `livekit-agents` + `livekit-plugins-google` and RTC dependencies; same Google credentials/billing. | Less provider plumbing, larger dependency/worker surface. Standalone STT does not need an LLM/TTS AgentSession. Consider later if justified. |
| LiveKit Inference streaming STT | RTC/Agents inference SDK, Cloud credentials and explicit model/provider approval. | Fewer credential sets, but changes the documented provider boundary and adds metered inference. Existing media allowance does not establish STT entitlement. |
| Groq Whisper buffered chunks | Existing Groq SDK/key plus RTC and in-memory audio encoding. | File transcription, not bidirectional streaming. Chunk boundaries/delays/deduplication and ten-second minimum billing per request make it a poor first streaming slice. |

Pin compatible versions only when implementing. Official sources checked
12 October 2026: [standalone LiveKit STT](https://docs.livekit.io/agents/models/stt/),
[Google plugin](https://docs.livekit.io/agents/models/stt/google/),
[Google streaming](https://docs.cloud.google.com/speech-to-text/docs/v1/transcribe-streaming-audio),
[Groq file STT](https://console.groq.com/docs/speech-to-text).

Google V2 standard starts at $0.016/audio-minute: two continuously processed
30-minute speaker streams are approximately $0.96 before LiveKit/taxes/credits.
V1 currently lists 60 free minutes/month and $0.024/minute afterward without data
logging. Different API/model pricing applies; unused allowance is not verified.
Do not enable data logging for a discount. [Google pricing](https://cloud.google.com/speech-to-text/pricing).

LiveKit Build advertises $0/month and $2.50 inference credits; model charges vary
(e.g. Nova-3 monolingual $0.0048/minute). Additional subscriber participant-minutes,
transfer and hosted-worker costs must be considered separately. Actual project
credits/quotas are unverified. [LiveKit pricing](https://livekit.com/pricing),
[limits](https://docs.livekit.io/deploy/admin/quotas-and-limits/).

**Do not activate a paid service without owner approval.** Verify Google API,
billing, quota, model/region, retention terms and a small spending cap first.
Existing LiveKit credentials do not prove Google readiness.

## Smallest implementable slice

One isolated interview, two consenting synthetic participants, English captions,
maximum **two minutes** of STT. No full Co-Pilot, LLM/TTS, recording, downloads,
database transcript table, checkpoint transcript or replay.

1. **Consent:** both authenticated roles explicitly accept the named provider,
   processing purpose, transient captions and stop control. Recruiter cannot consent
   for candidate. Check ownership, current invitation/session, revision, join window
   and connected role identities. Start only when both consent; any withdrawal
   closes the gate. No audio subscription or provider stream before then.
2. **Audio:** one server-only room-scoped, subscribe-only RTC participant selectively
   receives the two authorized microphone tracks, never video, screen-share audio
   or unknown participants. It is an integration task, not another LangGraph workflow.
   Identify it as a transcription service rather than a third human in the UI.
3. **Captions:** one STT stream per role, proposed mono 16-kHz signed PCM16 with
   bounded in-memory conversion/queues. Proposed 100-ms frames are 3.2 KB. Validate
   actual audio format. Google V2 permits 25-KB messages and five-minute streams;
   the two-minute proof avoids implementing long-session rotation immediately.
   Emit bounded segment ID, session generation, role, sequence, relative timing,
   text and interim/final flag. Replace interim text and deduplicate finals.
4. **Stop:** either role can cancel. Disconnect, revocation, stale authorization,
   window/timer expiry, overflow, provider failure or backend shutdown also stop
   captions. Cancel/await streams, unsubscribe, disconnect observer, clear audio
   buffers/captions and drop late events. Reconnect requires fresh consent. Keep
   A/V usable; no silent retries, backfill or provider fallback.

[Google stream limits](https://docs.cloud.google.com/speech-to-text/docs/quotas).

Speaker labels come from server-authorized microphone ownership, not an LLM,
client role claim or guessed diarization. This proves stream provenance, not voice
identity: echo/cross-talk can put another voice in a track. Use headphones.
Captions are not automatically hiring evidence.

Use authenticated FastAPI WebSockets for consent/status/captions with exact Origin
checks and owner/session authorization; candidate routes must remain under the
existing `/api/v1/interview-access` cookie path. No tokens in socket URLs or broader
human LiveKit grants. Rate-limit controls and bound event payloads.

For this isolated proof, use one FastAPI worker with transient consent/task state,
one task per interview and concurrency-safe start/stop. Restart/control-connection
loss fails closed. Multi-worker coordination/durable consent audit are later work.
Bound queue duration, caption count/text length and lifetime; never buffer a whole
interview. Render escaped React text; no content/tokens in logs, files, browser
storage, PostgreSQL, telemetry or checkpoints. Logs contain only fixed categories
and numeric timings/counts. No app persistence does not guarantee provider zero
retention: approve provider policy separately. Current media is not application
E2EE; adding an STT reader extends the trusted audio-processing boundary.

## Proposed files and tests

Later create `backend/app/integrations/stt/google_streaming.py`,
`backend/app/services/interview_transcription.py` and
`backend/app/schemas/interview_transcription.py`; extend existing interview/access
routers and `LiveInterviewPage.tsx` / `api/livekitInterview.ts`. Reuse authorization,
not a new agent, interview schema or dashboard. No migration for ephemeral captions.

Test missing/one-sided/withdrawn consent, concurrent starts, foreign owner, revoked
invitation, wrong track/role, stale revision/window, interim/final ordering, safe
text rendering, provider auth/429/timeout, silence, invalid audio, overflow,
disconnect and late-event cancellation. Verify no persistence or log leakage.
Deterministic fake-provider tests must be labeled mocked. After billing approval,
run a two-minute real synthetic proof; proposed targets are interim <=2 seconds,
final <=5 seconds after speech ends and cleared captions <=1 second after stop.
Measure these; they are not provider guarantees. Then user-consented physical Edge
checks. Cross-network, code-switching, long interviews and five-minute stream
rotation remain separate verification.

## Viva decisions

STT transcribes; it does not reason about or score candidates. Separate streams
provide role provenance without semantic guessing. Both-party consent is an
authorization gate. Cancellation must suppress late output as well as future
audio. Temporary captions are not permanent transcripts. The first proof preserves
the existing interview and stops safely on STT failure; it does not complete F4 or
the LangGraph Co-Pilot. No trainer-owned WBS/SRS changes are made here.
