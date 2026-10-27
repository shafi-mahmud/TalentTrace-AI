# Optional synthetic-only AssemblyAI → F4 captions → F11 demonstration

This historical fixed replay is distinct from the later
[Task 4 live-development F4 implementation and acceptance](task4_assemblyai_live_20261027.md).
The new opt-in flag accepts authenticated browser PCM, supports separate optional
storage and does not require F11. This document's replay contract stays unchanged.

Initial implementation increment, 20 October 2026: not activated or externally
exercised at that point. Later attempt diagnosis and offline fix are recorded below.
The release checkout and running environments are unchanged. No new provider
request was authorized/executed during implementation. No paid plan or fallback.

## Safety boundary and configuration

Default `ASSEMBLYAI_SYNTHETIC_ENABLED=false`. The existing local CPU recognizer
remains the default. To opt in on a separately approved isolated backend session:

- `ENVIRONMENT=development`
- `LIVEKIT_SYNTHETIC_DEMO_ENABLED=true`
- `INTERVIEW_COPILOT_ENABLED=true`, `INTERVIEW_COPILOT_LIVE_ENABLED=true`
- `TRANSCRIPT_STORAGE_ENABLED=false`
- `ASSEMBLYAI_SYNTHETIC_ENABLED=true`
- `ASSEMBLYAI_SYNTHETIC_INTERVIEW_ID=<exact authorized synthetic interview UUID>`
- `ASSEMBLYAI_API_KEY` supplied only through ignored private/session configuration.

These are implemented settings, not instructions to activate now. Other existing
LiveKit/auth/database configuration must still be valid. Use the optional existing
`backend/requirements-stt.txt` environment; no dependency was added or installed.
No migrations or assessment writes. Single backend worker/single-room development
bound remains; process-local state is not a distributed quota/security mechanism.

When enabled, caption sockets reject any other interview and ALL browser binary
PCM, even from a forged client. The adapter has no arbitrary audio/path parameter:
only the two source-owned eSpeak WAVs in `app/integrations/stt/synthetic` can be
read, and fixed SHA256s plus PCM format are checked before any connection.
Changing a checkbox cannot make microphone/candidate audio eligible for upload.
LiveKit physical media is a separate path; use generated media for both browser
participants for this demonstration. No microphone capture is needed or approved.

Free-tier AssemblyAI may use submitted synthetic audio/text for training. The UI
explicitly discloses that before caption consent. This is not appropriate for
private interviews. Existing app invitation/session/ownership/criteria/join-window
checks are unchanged. No provider key is returned to the browser or logged.

## Small lifecycle interface change

`CaptionSession._publish_caption()` extracts the existing safe event envelope and
bridge/storage dispatch from `_decode()`. Local stateless decoding and its sample
accounting retain their behavior. A separate `SyntheticStreamingCaptions` lifecycle
subclass reuses peers, consent, authorization, run identity, cleanup and bridge.
It does NOT call `transcribe()` for four-second chunks.

Both authenticated roles consent first; no external stream opens at consent.
The existing LiveBridge is attached to the same authorized sockets. Recruiter
prepares a new assistant run; both roles separately consent to F11. Then the
recruiter explicitly clicks **Start fixed synthetic cloud replay**. Server checks
both participant authorizations and live assistant context and waits beyond the
F11 pre-consent audio cutoff before opening a provider stream.

One recruiter stream sends the exact question, terminates and requires server
`Termination`, then emits one complete recruiter caption. Only then a separate
candidate stream sends the exact answer and follows the same lifecycle. 100ms
PCM16 frames are paced in real time; final tail frames exceed50ms. Provider partials
and unformatted finals never publish. Formatted finals are keyed by turn_order;
identical duplicates are ignored, conflicting finalized revisions fail closed.
Per-role text is bounded to1000 characters. Source audio send times are mapped to
the existing caption start clock; recognition/termination latency does not become
a fabricated audio interval. Global caption sequence and role remain server-owned.

The adapter requests `universal-streaming-english`, `format_turns=true` to preserve
question punctuation. Unlike the earlier unformatted benchmark, this exact setting
is not externally verified yet. F11's requirement for a question then answer is
unchanged: missing question punctuation/recognition may cause honest abstention.
No ground-truth transcript is substituted for provider output.

F11 receives only the normal safe caption envelope through `LiveBridge.offer`.
It still checks independent consent, scope, run generation and fresh database
authorization before calculating/publishing. Candidate assistant projection never
contains the recruiter suggestion. Captions themselves remain visible to both.

## Finish, withdrawal and failures

Only two sequential role streams per explicit attempt, each with21s work budget,
24s termination deadline and at most0.7s additional socket-close wait: nominal
combined client connection/cleanup bound49.4s. No retries, reconnects or fallback.
The configured interview has one replay attempt per backend process, even after
caption session replacement; process restart resets that guard and is not a retry
workflow. New external attempts always need separate approval.

Normal finish waits for accepted server replay, flushes final provider output,
then stops the caption/assistant lifecycle. Captions/suggestion remain reviewable
after automatic replay completion until withdrawal/finish/expiry; no provider
connections remain open after completion. Do not click Finish until reviewing a
settled suggestion if the purpose is to demonstrate F11.

Caption withdrawal/disconnection fences output immediately and cancels replay.
Independent F11 withdrawal or changed authorization is checked during streaming
at0.25s intervals (database checks bounded to2s), before each role and before
publication. It cancels streaming too. This is bounded polling, not instantaneous
revocation of already transmitted audio. LiveBridge independently rejects late
or pre-consent events. Network/API errors stop the whole run before another role.

On success, error or cancellation, the stream attempts `Terminate`, waits for
`Termination` within its remaining deadline and closes the socket in finally.
A cleanup status reports acknowledged versus unconfirmed termination to the
participants. A client deadline/closed socket does not guarantee that provider
billing stopped or training data was erased. Unconfirmed termination requires
checking provider usage; never automatically retry. No raw audio recording,
transcript logging or durable runtime transcript storage is introduced. The two
fixed synthetic source fixtures are intentionally retained in Git.

## Offline evidence and remaining real acceptance

Offline tests use fake WSS (network blocked) and the actual adapter, caption
session, LiveBridge, delivery manager and deterministic LangGraph. They verify
fixture-only framing; consent/authorization; finalized deduplication; role and
question-before-answer ordering; real bridge suggestion and candidate minimization;
late-result fencing; caption/F11 withdrawal; expiry; normal finish; transport/API
failure; acknowledged/unconfirmed termination; and process attempt limits.
Frontend production handlers verify no AudioContext/PCM in synthetic cloud mode,
explicit recruiter action, candidate control exclusion and mode mismatch rejection.

Exact commands, from backend, using an existing optional-STT Python environment:

```sh
python -B -m pytest -p no:cacheprovider tests/test_assemblyai_synthetic.py tests/test_interview_captions.py tests/test_copilot_live.py tests/test_copilot_delivery.py tests/test_interview_copilot.py tests/test_livekit_interview.py tests/test_interview_access.py -q --tb=short
```

From frontend: `pnpm test`; `pnpm build` (includes TypeScript).
The optional real local-Whisper gate is skipped without
`TRANSCRIPT_REAL_WHISPER_MODEL`; no model download or PostgreSQL gate is needed
for this interface-only increment. Database authorization is exercised with the
existing synthetic SQL fixtures, not an actual PostgreSQL database.

Minimum separately approved real demonstration: two generated-media browser roles,
one exact configured synthetic interview, both cloud-caption consents, both F11
consents, then one recruiter replay click. Maximum two sequential provider sessions,
nominal49.4s client connection/cleanup bound, no retries. Verify actual finalized
captions, question recognition, recruiter-only follow-up, provider termination,
and clear-on-withdrawal. An active-stream withdrawal test needs another separately
approved attempt; it cannot also complete the same question/answer trial. Record
actual latency and server usage rather than reuse earlier benchmark timing.

No real integration latency, natural speech accuracy, browser acceptance or
production privacy acceptance is claimed. Self-hosted LiveKit cached-JWT revocation
limitation is unchanged; this adapter does not repair media-token revocation.

Official protocol references checked:
- https://www.assemblyai.com/docs/streaming/label-speakers-and-separate-channels
- https://www.assemblyai.com/docs/coding-agent-prompts

## Verification recorded for this increment

- Focused backend/F3/F4/F11/auth suite above: **185 passed, 1 skipped**,31.74s.
  This includes22 new synthetic adapter/lifecycle/boundary tests. The skip is the
  explicitly configured real-Whisper gate, not an external AssemblyAI test.
- Full frontend suite: **244 passed,0 failed,0 skipped** (includes2 new cloud-mode
  production-handler tests).
- `pnpm build`: TypeScript and Vite production build passed. Existing >500kB
  LiveInterviewPage chunk warning remains; no bundle redesign in this increment.
- `git diff --check`: passed.
- Real provider calls in this implementation increment: **0**.
- Real integration/browser latency and real formatted-recognition follow-up:
  **not measured/not verified**. Earlier benchmark2.3s timings are not reused.
- Branch: `codex/f4-assemblyai-synthetic`; base HEAD
  `36047ef9cdaff43f574be7a331be8f5f860edabe`. Initial changes were left uncommitted for review; final review and Git
  preservation are recorded below. No pushes/merges or runtime activation.


## Final review — 20 October 2026

Reviewed all intended source, test, fixture and documentation changes. The local
Faster-Whisper provider files are unchanged; cloud mode remains default OFF.
Found and fixed one lifecycle defect: a receiver failure/early Termination could
otherwise allow the sender to continue transmitting remaining synthetic frames.
The sender now checks receiver completion before each frame and stops immediately;
two fake-WSS regressions cover provider Error and premature Termination. Cleanup
still attempts Terminate and reports acknowledgement honestly.

Revalidated focused suite: **187 passed, 1 skipped**. The skip is specifically
`test_real_caption_route_starts_two_local_workers`: no
`TRANSCRIPT_REAL_WHISPER_MODEL` was supplied. It is not an AssemblyAI acceptance
test and does not download a model. Frontend source is unchanged from the recorded
244-pass/TypeScript/production-build validation above.

Existing isolated runtime read-only check: backend8000 and frontend5173 return200;
LiveKit remains loopback7880/7882; PostgreSQL container tt-f11-home-41166262 serves
only the isolated f11_home_demo database at54403, revision0015. Existing candidate
invitation expired at18:06 Asia/Dhaka and its interview join window is closed.
Owner and criteria remain valid. Current services still load the release source,
not this worktree. No runtime settings, invitations or records were changed.

Real browser acceptance remains BLOCKED pending explicit approval for a fresh
synthetic interview fixture (preserve the expired fixture, do not rotate its
one-use invitation), worktree runtime activation, and one two-session AssemblyAI
demonstration. Reconfirm free credits, no payment/top-up and synthetic-only training
exposure before opening any provider connection. Maximum two sequential streams,
no retries, nominal49.4s client bound; stop on a failed acceptance stage. Normal
finish acceptance cannot establish active-stream withdrawal behavior. No new
provider call or real integration latency was measured during this final review.

## Prefaced-question fix — offline verification only

The approved real attempt on5809fad delivered both final role captions through the
trusted bridge, but no follow-up: ASR began `In Python, our list mutable, explain
how...` without a question mark. The old anchored detector never opened a question
context. Python/SQL requirements and answer-topic overlap were valid and unchanged.
Exact synthetic recognized texts are retained in the regression test; no correction
or artificial punctuation is applied to the provider evidence.

`workflow.is_question()` now centralizes question recognition for dialogue assembly,
exploration tracking, answer-as-question rejection and independent output validation.
Supported direct question starts remain. Explicit question clauses may follow a
bounded topic introduction (`in`, `for`, `about`, `regarding`, `on`, `with respect to`,
`on the topic of`): first fragment <=8 words/limited characters, optional second
noun-like fragment <=5 words, at most2 fragments. Arbitrary narrative prefixes,
quoted/reported instructions and negated commands fail closed. A standalone nominal
question with trailing? is limited to8 words and cannot contain narrative clauses.
Recognition does not rewrite stored events, stem requirement descriptions, infer
technical competence or relax answer relevance, exact binding, generation, source,
authorization, consent or candidate-delivery checks.

Exact recognized question/answer offline replay now yields:
- status=`suggested`,reason=`valid_suggestion`;
- criterion=`skill-0` (Python),kind=`example`;
- `Could you walk through a concrete example related to this requirement: Python?`;
- source sequences1,2, same consistent caption-run identity.

Original live run/caption UUIDs were not logged; the replay uses consistent surrogate
IDs while retaining actual revision, requirements, roles, sequence, audio intervals
and text.4s settling is allowed. No provider request or transcript substitution.
The corrected result does not establish a successful live/browser retest or latency.

`copilot_live.graph_result_metadata()` reads `Result.suggestions` (plural) and returns
only status, reason, suggestion presence/count. The ignored local diagnostic launcher
now calls this helper and no longer logs transcript bodies. Existing synthetic
attempt evidence is preserved; the already-running process was NOT restarted or
activated with these changes. No logging of credentials or private speech is added.

Verification from backend with existing optional-STT Python:

```sh
python -B -m pytest -p no:cacheprovider tests/test_copilot_prefaced_questions.py tests/test_assemblyai_synthetic.py tests/test_interview_captions.py tests/test_copilot_live.py tests/test_copilot_delivery.py tests/test_interview_copilot.py tests/test_livekit_interview.py tests/test_interview_access.py -q --tb=short
```

**234 passed,1 skipped** (54.78s), including47 new prefaced-question/bridge/metadata
cases. The skip remains the explicitly configured real local-Whisper worker gate.
Frontend source is unaffected; frontend tests/build were not rerun for this backend
fix. Earlier244-pass frontend validation remains historical evidence only.
`git diff --check` passed. Zero new AssemblyAI requests. No live session restart,
activation, requirements/DB changes, pushes, merges or other-worktree edits.

Limits: this is a conservative English surface grammar, not general intent/semantic
recognition. Unsupported long/narrative introductions, quoted technical identifiers,
or reported/negated phrasing may abstain even when a human could understand them.
ASR errors, missing requirement tokens or uncertain/irrelevant answers can still
prevent suggestions. Free-tier training exposure and LiveKit JWT limitations remain.

## Final offline UI verification — 20 October 2026

No provider request, microphone capture, interview replay, database reset or live
backend restart. Original final-attempt evidence and exclusive attempt lock remain.
Source before this check:fb6221f. The previous real attempt's rendering remains
unestablished; the following is new OFFLINE verification, not a live retest.

Real `api.validStatus` and `InterviewCopilot` handlers were exercised with controlled
synthetic status responses and virtual timers. Successful polls render the article
across eight samples of a15s server-result window, then remove it on the next poll.
No competing manual refresh bypasses the one-request guard. A prior failed prepare
can recover on a later valid poll. Withdrawal clears the article synchronously;
late polls/leave cleanup cannot restore it. Existing run-expiry cleanup and candidate
field rejection remain verified. No TTL, response-fence or authorization changes.

The real React component, production API validator and production CSS were also
bundled into a disposable local browser fixture using existing packages. All fetches
were mocked, CSP connect-src none blocked real network connections, and no live
interview/account/session endpoints were used. Browser DOM/screenshot confirmed a
visible recruiter Provisional follow-up, candidate article count0, removal after
the result window, and article count0 immediately after withdrawal. Temporary tab
and fixture server5199 were closed after verification. The ignored private proof
is data/f11-ui-offline-20261020/suggestion-visible.png.

No independent rendering defect reproduced. Actual LiveInterviewPage places F11
above transcript/analysis/captions; it can be offscreen while watching captions.
The15s result lifetime can explain missed human observation, but retained evidence
cannot prove why the earlier browser did not show it. No autoscroll, toast, TTL
extension or privacy relaxation was added merely to force live acceptance.

A separate disclosure defect DID reproduce: cloud synthetic mode still returned
F11 wording claiming no external AI provider, and a Local F4 header. Fixed only that
confirmed issue. `disclosure()` now supplies consistent mode-specific config/status
wording; config exposes non-sensitive `synthetic_cloud`. The UI distinguishes
AssemblyAI's fixed synthetic transcription/model-training exposure from local F11
processing and uses mode-aware consent wording. Local mode retains its original
wording. Both consents and default-disabled provider gate remain unchanged.

User confirmed sign-out in the existing synthetic recruiter profile. Read-only
isolated DB metadata showed active synthetic sessions5->4; remaining historical
sessions were not revoked. The actual exposed cookie was never reused/revealed.
The existing offline logout regression signs out, reuses a synthetic test cookie
and verifies401; this confirms route behavior without transmitting the exposed
credential. It is not an independent replay check of that actual cookie.

Tests:
- `node --experimental-strip-types --test frontend/tests/copilot.test.ts`:
  **16 passed** (includes5 new handler/privacy cases).
- Backend from backend directory, existing optional-STT Python:
  `python -B -m pytest -p no:cacheprovider tests/test_copilot_delivery.py tests/test_copilot_live.py tests/test_copilot_prefaced_questions.py tests/test_interview_copilot.py tests/test_assemblyai_synthetic.py tests/test_interview_captions.py tests/test_recruiter_records.py -q --tb=short`:
  **229 passed,1 skipped** (47.43s); skip remains explicitly configured real Whisper.
  Includes2 new mode-specific disclosure cases and real logout-route synthetic regression.
- Full frontend `pnpm test`: **249 passed,0 failed,0 skipped**.
- `pnpm build`: TypeScript/production build passed; existing >500kB chunk warning.
- Diff checks passed. Source and tests contain no credentials or private recordings.

Conclusion: offline React UI rendering/lifecycle PASS; misleading cloud disclosures
fixed. Live user-visible acceptance/latency for the prior provider run remains
PARTIAL/unverified. No new external attempt is authorized by this verification.
