# Two bounded capture epochs: technical proof

Based on `f1871faa2ba99698ecc0492f89b01f9e3f388dfb`, branch
feature/f4-bounded-capture-epochs. No migration, new service or frontend change.
This is not automatic rollover or complete 15–30-minute interview support.

## Existing machinery reused

One scheduled interview already accepts multiple InterviewTranscriptSession rows.
The partial unique active-interview index permits only one active capture at a time.
TranscriptConsentCoordinator.prepare preserves the active capture, but after a
terminal capture creates a new ID with empty receipts. Each role must explicitly
accept again; signed receipts bind role/actor/interview/capture/version/time and
cannot authorize the following capture. Existing 300-second receipt-age checks
remain unchanged. Durable interview-wide revocation fences every persistence write.

The connected proof now executes: schedule -> independent storage/caption consent ->
bounded capture A -> drain and persist completion (or explicit interrupted state) ->
three-second synthetic transition -> fresh prepare and both storage/caption consents
-> bounded capture B -> normal finalization -> persisted F5 -> reloaded F6.
Both captures retain the same recruiter/job/batch/upload and criteria revision.
No production timer, role projection, consent rule or resource limit was relaxed.

Each CaptionSession receives the SAME absolute authorized deadline, computed once
from this interview's join deadline; candidate invitation expiry is later in the
fixture. Starting B does not extend that deadline. A separate clock test confirms
both sessions expire at the original deadline. Existing finalization grace can drain
already accepted audio for up to 35 seconds; it is not a renewed capture capability.
The real WebSocket authorization watcher/transport is not exercised by this service test.

## Evidence and gap semantics

Capture IDs and persisted start/end timestamps already represent window boundaries;
each turn remains bound to a capture UUID with a per-capture sequence and speaker.
The same sequence values in A/B do not collide. Exact duplicate old events are
idempotent within their original capture; new late events to a closed capture fail.
Late old-capture consent cannot authorize B. Wrong job, actor and candidate interview
are rejected using normal authorization paths.

Small production change: build_input derives a deterministic transition warning from
the persisted windows, naming adjacent capture IDs and the gap in milliseconds.
It explicitly says transition audio coverage, including around boundaries, is
unverified. Window gaps are not precise measurements of every missing utterance.
Overlapping windows are refused (including sub-millisecond overlap), not silently
ordered into apparently continuous evidence. No separate gap table or transcript
content copy was added. Single-capture warning behavior remains unchanged.
The warning lists at most five transitions and explicitly counts any additional
ones; all capture-window identities/times remain in the persisted source. This
keeps the existing 2,000-character frontend analysis-warning contract intact.

F5 already groups dialogue by capture: it never pairs an answer across epochs.
Boundary uncertainty remains visible. Both complete epochs are loaded under the same
ownership/revision/retention checks; source-linked output and the warning persist
through durable analysis. F6 reloads/validates those exact source turns and exposes
the warning through its existing field/UI. A partial nonempty first capture blocks
evaluation even when B succeeds. No partial recognized speech is silently discarded.
An empty failed attempt retains the existing explicit exclusion warning behavior.
The new multi-capture warning changes its input fingerprint; old multi-capture
analysis may be treated as stale, never silently reused or automatically re-inferred.

## Verification

- Connected PostgreSQL suite: **8 passed**, zero failed/skipped. Four original
  single-capture variants plus two complete epochs, interrupted-first/complete-second,
  revocation between epochs and missing candidate consent for B.
- Offline focused suites: **109 passed, 23 deselected**, zero failed/skipped,
  including eight new epoch-contract cases and existing caption finalization,
  consent, evaluation-input, Q&A, evaluation and F6 projection tests.
- Final combined connected/epoch-contract command: **16 passed**
  (the eight contract tests overlap the offline count; do not add them twice).
- New checks cover distinct IDs, speaker attribution, a three-second persisted gap,
  late/duplicate events, missing consent, revocation blocking new preparation AND old
  persistence, cross-scope refusal, absolute deadline, unchanged PCM/event limits,
  overlapping windows, incomplete history and correct F5/F6 references.
- An initial edit command used the wrong directory and made no change; an unchanged
  baseline run passed four cases. No production failure was hidden by that run.
- Python syntax/diff checks passed. No frontend change means no frontend build needed.

From backend with the existing approved disposable pg fixture:

```powershell
$env:TRANSCRIPT_PG_TEST='1'
python -B -m pytest tests/test_interview_assessment_flow.py tests/test_capture_epoch_contract.py -q
$env:TRANSCRIPT_PG_TEST='0'
python -B -m pytest tests/test_capture_epoch_contract.py tests/test_caption_finalization.py tests/test_transcript_consent.py tests/test_evaluation_input.py tests/test_interview_qa.py tests/test_interview_evaluation.py tests/test_consolidated_assessment.py -q -rs -k 'not pg'
```

Real components: PostgreSQL, scheduling/authentication, consent/persistence/finalization,
LangGraph, durable F5 storage and F6 source validation. Simulated components: claimed
session provisioning, socket peers, deterministic speech/model providers and clocks.
No external inference, microphone/browser/media, F11, N19 deletion or preserved DB.
Only the fixture's new container is started/stopped; existing services remain intact.

## Full-duration limits / next decision

All limits in [the connected-flow record](interview_assessment_integration.md) remain:
120-second default, 300-second isolated maximum; four-second bounded pending PCM;
120–150 events and 150 acknowledged turns per capture; capped sample counts;
100 captures/1,500 turns and 50 Q&A pairs per evaluation; consent/revocation,
authorization deadlines, retention and finalization timeouts still apply.

Ignoring gaps/overhead, 15–30 minutes needs at least 8–15 default 120-second epochs,
or 3–6 isolated 300-second epochs. This arithmetic is not performance readiness or a
claim of gap-free coverage. The proof deliberately tests only TWO epochs and adds
no interview-level continuation budget manager or automatic browser orchestration.

Recommended next priority: Docker integration/reproducibility for this bounded,
truthfully scoped workflow. Do not expand epoch counts until total interview budgets,
transition UX, reauthorization, restart recovery and bounded F5 analysis beyond its
turn/pair limits have an approved design. A full-duration requirement remains open.
