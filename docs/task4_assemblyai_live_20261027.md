# Task 4 — opt-in AssemblyAI live F4, 27 October 2026

## Implemented boundary

The existing authenticated caption WebSockets now support a separate live
development provider. Browser AudioWorklet PCM goes through the existing bounded
socket; the backend opens one independent AssemblyAI V3 stream per authenticated
role. Role, interview, owner and criteria revision come from existing server
authorization, not audio messages. LiveKit and its token flow are unchanged.

The fixed server-owned WAV replay remains separate under
`ASSEMBLYAI_SYNTHETIC_ENABLED`; its F11/no-storage contract is unchanged. Local
Whisper is separately configured, never an automatic fallback. Normal F4 live
captions require no F11 consent. Optional PostgreSQL storage still needs separate
two-party storage consent before caption capture.

Implemented settings (all credentials/identities stay private):

```text
ENVIRONMENT=development
LIVEKIT_SYNTHETIC_DEMO_ENABLED=true
ASSEMBLYAI_LIVE_ENABLED=true
ASSEMBLYAI_LIVE_INTERVIEW_ID=<one approved synthetic interview>
ASSEMBLYAI_API_KEY=<backend-only private credential>
ASSEMBLYAI_SYNTHETIC_ENABLED=false
TRANSCRIPT_STORAGE_ENABLED=true
```

Leave `LOCAL_CAPTION_MODEL_PATH` unset in live mode. Settings reject production,
missing key/scope or ambiguous simultaneous local/replay configuration. Keep
F5/F6 inference, F11, SMTP, publishing and biometrics disabled for this proof.
The ordinary runtime defaults remain disabled; no migration/model download was
introduced. Existing schema `0017_booked_interview_email` supports this storage.

## Protocol, timing and failure handling

Current official [V3 message documentation](https://www.assemblyai.com/docs/streaming/message-sequence)
and [WebSocket specification](https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket)
were reviewed. The adapter explicitly requests `universal-streaming-english`,
`format_turns=true`, mono 16 kHz PCM16. It verifies the model echoed by Begin.
Only formatted end-of-turn results publish. Repeated identical finals are ignored;
conflicting finalized revisions stop the run and leave incomplete capture status.
Partials, unformatted finals and empty closing markers are not stored as turns.

Word offsets must lie inside accepted audio. A bounded per-role sample timeline
maps them to server-observed capture intervals, including mute gaps; recognition
return time is not presented as speech time. Sequences describe publication
order, not guaranteed global audio chronology across two independent streams.
These timestamps remain ASR/server estimates, not ground truth.

Both peers consent before any provider stream opens. One process-local attempt
per configured interview is reserved before opening either stream. Startup/send
timeouts, a 90-second normal-capture guard and independent 110-second stream
watchdogs bound usage. Termination acknowledgement is bounded to five seconds,
then socket close to one second (nominal maximum under 120 seconds per stream).
No reconnect, retry, provider fallback or raw audio recording is implemented.
Process restart resets the in-memory attempt set; it is not a durable billing
control or permission to repeat a trial. SDK frame/header logging is disabled.

Normal finish flushes existing worklet accounting, waits for both role ends and
provider termination, then uses existing trusted event persistence/finalization.
Processed-sample accounting is capped by provider-reported processed duration;
a short acknowledgement produces partial status rather than invented coverage.
Cloud-caption withdrawal fences further caption output and closes both streams.
Storage withdrawal separately fences/deletes durable text; it does not withdraw
an otherwise valid temporary-caption permission. Neither erases audio already
sent to the provider. Unconfirmed termination requires a usage check, not a retry.

## Acceptance results

| Boundary | Evidence/result |
| --- | --- |
| Free-tier gate | Owner confirmed trial/free, no paid billing/autopay and one bounded synthetic test. Supplied dashboard showed Free and about $49.99646 credits before the attempt. No upgrade or purchase. Post-test credit balance was not independently reread. |
| Real external recognition | PASS at authenticated API boundary: two actual AssemblyAI streams, four nonempty formatted caption turns, both server-assigned roles, unique sequences and validated relative intervals. Generated client PCM came from checksum-verified existing eSpeak WAVs. No transcript text was inserted. |
| Provider termination | Both acknowledgements received, no provider errors; reported audio duration 15 seconds per stream and session duration 18/16 seconds. Total provider session time 34 seconds; whole test 23.469 seconds including fixture/auth setup. No retry. |
| Storage and reload | Real fresh PostgreSQL 0017: all four turns committed; completed/saved status and identical turn identities on a subsequent authenticated GET. No F11 enabled. |
| Withdrawal/deletion | After normal completion, candidate withdrawal reported verified deletion; subsequent recruiter transcript retrieval was denied. Actual mid-stream withdrawal was tested with mocks, not another external run. |
| Declining storage | Real PostgreSQL plus fake provider: temporary captions still work; transcript review is denied after decline. Not repeated against AssemblyAI. |
| Isolation | Real authenticated API tests reject foreign owner/recruiter-caption access and candidate transcript/assessment access; candidate identity uses the invitation exchange cookie. No auth dependency override. |
| Browser AudioWorklet | Production handlers tested with mocked browser APIs. Combined browser AudioWorklet → actual AssemblyAI, browser transcript refresh and mute-gap timing were not externally accepted. Task 3's Cloud media PASS is separate evidence. |

The external test used real application routes in Starlette's in-process test
transport, an actual new PostgreSQL container and actual provider WebSockets.
It did **not** start a deployed HTTP backend/frontend, perform a LiveKit Join,
or establish browser STT acceptance. Fixture scoring alone used existing
deterministic test helpers. The actual recognizer was not mocked in that attempt.
The fixture's unused LiveKit configuration only allowed normal local invitation
issuance; it was not connected or verified as a working Cloud joining destination.
No assertion of recognition accuracy, long interviews or full BID completion.

## Tests, subsequent correction and runtime preservation

- Focused backend: **102 passed, 1 skipped**. The skipped check requires an
  explicitly selected local Whisper model; no model was downloaded.
- Separate authenticated/PostgreSQL mocked-provider cases: **2 passed**.
  These are additional tests, not included in the 102 above.
- Frontend: **28 passed**, no skips; TypeScript and production build passed.
  Existing >500 kB LiveInterviewPage warning remains.
- Test setup initially failed on cached async engines across event loops,
  httpx/httpx2 URL types and the required storage consent-version header. Test
  helpers were corrected; production authorization was not weakened.
- A legacy replay test's 10 ms settle raced mock transport yields. A test-only
  calculation gate makes it deterministic; no production F11 change.
- After external acceptance, focused offline review corrected the exact sample
  boundary at a mute gap and added an assertion, explicit transport-log suppression
  and connection/lifetime bounds. These were offline-validated; no second provider
  request was made to recheck them.

The ignored `data/task4-current.json` locates private Task 4 evidence:
`external-attempt-intent.json`, sanitized `external-result.json`, test output,
resource manifest and cleanup summary. No key, transcript, media, invitation URL
or private database configuration enters Git. Only the new test-owned PostgreSQL
container was stopped; its volume and evidence remain. Existing Groq Docker
container identities/start times and all other worktrees/databases are unchanged.
The existing app still serves its Task 3 build; this Task 4 build is not deployed.

## Files changed

- `.env.example`: separate disabled live settings.
- `backend/app/core/config.py`: explicit isolated mode and scope validation.
- `backend/app/api/routers/interview_captions.py`: select live provider behind
  existing authorization; expose nonsecret mode flags.
- `backend/app/services/interview_captions.py`: small provider/activation hooks;
  local lifecycle behavior preserved.
- `backend/app/integrations/stt/assemblyai_live.py`: bounded V3 adapter.
- `backend/app/services/live_streaming_captions.py`: role streams, timing,
  trusted publication and existing storage/finalization.
- `backend/requirements-stt.txt`: clarify optional dependency use; versions unchanged.
- `backend/tests/test_assemblyai_live.py`: fake-WSS/config/timing/cleanup cases.
- `backend/tests/test_assemblyai_live_persistence.py`: authenticated PG/API scenarios;
  refuses arbitrary database identity and never provisions during collection.
- `backend/tests/test_assemblyai_synthetic.py`: deterministic legacy test gate.
- `frontend/src/components/InterviewCaptions.tsx`: live disclosure/source validation,
  existing AudioWorklet path, explicit consent and termination status.
- `frontend/src/components/LiveInterviewPage.tsx`: pass generated-media selection;
  no LiveKit architecture change.
- `frontend/tests/captionLifecycle.test.ts`: live-mode and fail-closed UI cases.
- `docs/task4_assemblyai_live_20261027.md`: this evidence and walkthrough.
- `docs/f4_assemblyai_synthetic.md`: link historical replay to the distinct live mode.

## Recommended next browser walkthrough (another external attempt is not authorized)

1. Review/deploy the tested build with live mode still disabled. Preserve the
   existing app/database. Separately approve a new bounded browser trial after
   checking AssemblyAI credits and any needed LiveKit free allowance.
2. In an isolated development runtime at 0017, create a fresh eligible synthetic
   booking/invitation using existing UI/services. Configure its exact live scope
   privately; never rotate/reuse this test's invitation.
3. Open recruiter/candidate contexts, select generated media and approved local
   synthetic WAVs before joining. Never grant physical device permissions.
4. Join only under that new authorization. Independently review and accept optional
   storage **before** captions; declining keeps captions temporary.
5. Each role explicitly accepts the AssemblyAI disclosure and caption consent.
   Play generated speech through the existing microphone track/AudioWorklet.
   No fixed replay action or F11 consent is needed.
6. Verify role/timestamped captions, Finish captions normally before 90 seconds,
   acknowledged termination and saved status. Load transcript and refresh.
7. Exercise withdrawal/privacy cleanup, leave both roles and disable live mode.
   Stop at the first failure; never automatically retry a provider session.
