# Synthetic scheduled interview to consolidated assessment

Based on verified integrated develop `480184c`, 23 October 2026. This increment
adds tests, not a new F3/F4/F5/F6 implementation or a full-duration capture feature.

## Connected scenario

`backend/tests/test_interview_assessment_flow.py` connects these real boundaries:

1. Provision fictional owner/foreign recruiter sessions, a confirmed revision-2 job
   and an actual deterministic F2 score using existing synthetic screening helpers.
2. POST the normal authenticated interview scheduling API. Its owner, score,
   criteria revision, selection, overlap and future-time validations run unchanged.
3. Provision a synthetic already-claimed candidate session (invitation delivery and
   exchange are simulated), then call real storage-consent prepare/accept paths for
   both authenticated roles. No consent receipts or request.state identities are forged.
4. Feed bounded RAM-only PCM frames through CaptionSession with a deterministic
   recognizer. Real CaptionTranscript converts recognized events, appends to PostgreSQL,
   drains/finalizes and saves accepted/processed audio evidence. No real audio/model.
5. PostInterviewInputService reloads persisted turns and validates both roles,
   timestamps, source identity, consent, revision, retention and completeness.
6. DurableAnalysisManager runs the real LangGraph pairing/mapping/retrieval/evidence-
   validation workflow with the local curated retriever and a deterministic provider.
   The provider supplies a source-linked relevance quotation and abstains on the
   other dimensions; this is not real-provider accuracy evidence.
7. A fresh manager reads the persisted analysis. F6 reloads the exact saved CV and
   analysis using normal authenticated ownership checks and revalidates provenance.
   Two fresh database sessions return identical reports with original turn IDs.
8. Wrong job, wrong application and foreign recruiter reads are refused. Candidate
   cookie access to the actual F6 HTTP endpoint is 401. Stale revision is refused.

The four scenario variants are complete, interrupted, missing speaker and provider
failure. Interrupted/missing-speaker captures never invoke the evaluation provider;
failed inference yields no fabricated assessment. F6 does not label those unavailable
interview results as available. Reviewer confirmation is not submitted in this test.

## Disposable infrastructure and reproduction

Reuse the existing opt-in `test_interview_transcripts.pg` fixture. It reads only the
image tag of the preserved local PostgreSQL container, starts its own uniquely named
`talenttrace-transcript-test-*` container on 127.0.0.1:54402 with fresh storage, and
removes only that new container on teardown. It never connects to a preserved DB.
The fixture migration chain now includes 0015 for the F6 confirmation table; there
is no new migration or schema change. Existing local images and dependencies only.

From backend, with Docker Linux engine/local pgvector image and port 54402 free:

```powershell
$env:TRANSCRIPT_PG_TEST='1'
python -B -m pytest tests/test_interview_assessment_flow.py -q
```

HTTPX external transport is forbidden in the new test; ASGI requests stay in process.
The PostgreSQL connection is real and local. No browser, LiveKit participant,
microphone, provider credentials, external inference or production service is used.
Restart evidence is fresh manager/session retrieval, not a browser or OS restart.

Measured validation:

- Connected PostgreSQL scenarios: **4 passed, zero failed/skipped**, final run
  19.59 seconds. This includes fresh fixture migrations and real persistence.
- Focused existing offline suites: **74 passed, 23 deselected**, zero failed/skipped:
  `python -B -m pytest tests/test_caption_finalization.py tests/test_evaluation_input.py tests/test_interview_evaluation.py tests/test_consolidated_assessment.py -q -rs -k 'not pg'`
- Initial new-test failures were corrected: nested asyncio.run in a reused scoring
  helper (moved to a worker thread), invalid test-token format (replaced with normal
  synthetic token generation), provider-double signature/model return mismatch and
  missing current_recruiter call before direct F6 service invocation. Production
  authentication/validation was not bypassed to resolve them.
- Frame timing advances a test clock; no real-time eight-second microphone capture
  or 30-minute interview occurred. No frontend change/build or browser run was needed.
- Syntax and diff checks passed. Only new disposable fixture resources were stopped
  by normal test teardown; running office services and preserved databases stayed intact.

## Exact blockers to 15–30-minute capture

| Boundary | Current behavior |
| --- | --- |
| Server configuration | local_caption_test_duration_seconds defaults 120, range 120–300. Non-default duration requires isolated synthetic development configuration. |
| CaptionSession | Same 120–300-second bound; expiry stops capture. Sequence cap max(120, duration_seconds // 2), shared across roles. |
| PCM and memory | 16 kHz mono PCM16; normal frame 3,200 bytes; 128,000-byte four-second decode/pending buffers per role. Per-role accepted samples limited to duration * 16,000. Overflow stops, rather than dropping audio and claiming success. |
| Authorization | Join window ends interview duration +15 minutes; candidate invitation expiry can shorten it. Rechecked every second; recruiter authentication still applies. Waiting for caption consent has its own 120-second window. |
| Finalization | Server drain and durable finalization grace 35 seconds; client flush 2 seconds and overall finish timeout 40 seconds. Disconnect/timeout is not proof of complete capture. |
| Frontend | Defaults 120 and rejects active durations above 300; caption/finalization validators enforce duration/sequence/sample bounds. WebSocket backlog above 64,000 bytes stops capture. Only last 30 captions are displayed, distinct from persisted transcript. |
| Storage evidence | Per-role sample counts capped at 4,800,000 (300 seconds at 16 kHz); expected/acknowledged turns capped at 150 per capture; each turn text at most 1,000 characters. |
| Evaluation | At most 100 captures/1,500 turns and 50 Q&A pairs. Incomplete captures containing turns are not silently omitted. Default graph execution deadline 110 seconds. |

Thus a 30-minute scheduled booking does not imply a 30-minute transcript. Increasing
one duration constant would violate other contracts and could increase memory,
inference backlog and provider-input pressure. Existing short finalized accepted audio
is explicitly scoped accepted_audio_only, not evidence of a complete interview.

## Recommended next increment — design, not implemented

First prove two sequential bounded capture epochs for the same interview, with
normal drain/acknowledgement before starting the next epoch. Keep immutable capture
IDs, per-epoch sequences/timestamps, continuous consent/revocation checks and a shared
absolute interview deadline. Record transition gaps and interruption explicitly;
never silently renew consent or mark missing audio complete. Bound total epochs,
samples and persisted turns per interview and refuse exhausted budgets honestly.
The current multiple-capture input contract is reusable, but 1,500-turn/50-pair F5
limits need an explicit bounded analysis plan before promising 15–30-minute coverage.
Do not enable automatic continuation or relax limits as part of this test increment.

## Remaining acceptance / Docker gaps

This demonstrates service/data integration for short synthetic accepted audio, not
physical F3 media, microphone ASR quality, full interview recovery or browser print/
reviewer-confirmation acceptance. Baseline Compose contains DB/backend/frontend but
disables LiveKit, transcript storage, durable evaluation and reviewer confirmation.
It has no LiveKit service or provisioned local speech/reference models, and an
internal backend network cannot simply reach external evaluation providers. A full
documented deployment profile and separate clean-machine acceptance remain required.
N19 and screening-outcome feature branches are not integrated here; F11 stays frozen.
