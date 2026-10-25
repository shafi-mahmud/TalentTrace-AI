# F11 trainer finalization — 25 October 2026

Branch `feature/f11-trainer-finalization` starts at integrated trainer commit
`fd6a320fc99767b24adc971067d0e7b130aba7b1`, not develop. Analytics and publishing
remain included. The frozen experimental F11 branch was not merged.

Status: **implemented bounded functionality; live Cloud acceptance PARTIAL**.
No paid model or cloud fallback is added. This is optional question assistance,
not scoring, a hiring decision or a requirement that the recruiter ask a question.

## Verified code path

1. `backend/app/api/routers/interview_captions.py` authenticates role and interview,
   enforces origin/consent and selects local recognition. Browser traffic supplies
   bounded PCM, not accepted transcript text or a caller-selected speaker role.
2. `services/interview_captions.py` decodes and validates final captions, assigns
   sequence/time/source information and offers them internally to
   `services/copilot_live.py:LiveBridge`. There is no public speech-ingestion route.
3. Independent assistant consent pins the current caption run and F11 run/epoch.
   `api/routers/interview_copilot.py:access` checks owned job/interview, confirmed
   Job Reference and criteria revision, join window, invitation, pinned sessions
   and current access. It supplies approved requirement descriptors, not browser
   replacements. Caption consent, storage consent and assistant consent are distinct.
4. `services/copilot_delivery.py` and `agents/copilot/workflow.py` execute the
   model-free graph with requirement/source checks, question-before-answer rules,
   fragment settling and conservative abstention. Fresh authorization before
   publication plus generation/source fences suppress stale/withdrawn results.
5. Recruiter-only status projects an optional provisional question; candidate status
   omits suggestion/processing fields. Caption broadcasts never contain suggestions.
   `frontend/src/api/copilot.ts` validates role-specific responses and fences late
   responses; `InterviewCopilot.tsx` renders the question and explicit controls.
6. Run/result expiry, withdrawal, caption replacement and disconnection invalidate
   processing. Server authorization checks and client cleanup/TTL remain the
   fail-closed backstops; no instantaneous revocation of transmitted media is claimed.

## Confirmed UI defect and minimal fix

A status poll could be pending while the enabled **Dismiss / Ignore** button was
visible. Its action handler refused that click without feedback, leaving the card
visible for the network wait. A new regression first failed on that exact state.

The handler now permits dismissal to supersede the poll, as withdrawal already
could. Existing response generation fences prevent the older poll from repainting
advice. The card clears before awaiting dismissal, and the current run/epoch and
suggestion ID still go through the existing authorized dismiss endpoint. Consent,
retention periods, graph rules and server authorization are unchanged. Failure
remains unconfirmed/unavailable; no retry or broader evidence permission is added.

Changed implementation: `frontend/src/components/InterviewCopilot.tsx`.
Regression: `frontend/tests/copilot.test.ts` verifies immediate clearing, one
request, late-response exclusion and no withdrawal side effect.

## Acceptance boundary

The existing actual decode-hook test runs CaptionSession → LiveBridge → real graph
→ delivery using synthetic recognized speech from a fake recognizer, with role,
caption-run and audio-time assertions. It is concrete wiring evidence, not actual
speech recognition or Cloud browser acceptance. Tests also cover pre-consent audio,
wrong/stale/conflicting sources, unrelated/ambiguous answers, requirement changes,
withdrawal during calculation, expiry, access loss and candidate exclusion.

Frontend tests exercise the real component and validator with mocked APIs/timers:
positive polling, expiry, candidate minimization, explicit consent, disconnect,
withdrawal and now dismissal during a pending poll. They are not a new physical
browser observation.

Still needed: one separately approved fresh synthetic Cloud F3/F4 run with both
independent assistant consents, recruiter-visible question, overlapping candidate
API/DOM exclusion and one terminal lifecycle observation. Respect resource gates
and the frozen experiment's incomplete acceptance. Historical synthetic AssemblyAI
server/API evidence and offline React rendering do not prove live-browser visibility
or human-audio end-to-end acceptance. Candidate captions are intentionally shared;
the generated interviewer suggestion must remain recruiter-only.

Single-room, process-local state and short bounded lifetimes remain. Criteria
association is conservative/literal and can abstain on valid paraphrases. No new
Cloud call, microphone, booking, invitation, transcript storage, database mutation,
Docker build, external provider call, merge or push occurred here.

## Executed verification

- Focused backend graph, prefaced-question, bridge, delivery and API suites:
  **160 passed, 0 failed/skipped** (25.51 s).
- Focused frontend co-pilot suite: **17 passed**. Full frontend: **311 passed,
  0 failed/skipped**; the subset is included, not added again.
- TypeScript and production build passed; existing >500kB LiveInterviewPage bundle
  warning remains. Git whitespace checks passed.
- The new pending-poll dismissal regression failed before the fix and passed after.
  No unrelated implementation changes or new dependencies were necessary.
