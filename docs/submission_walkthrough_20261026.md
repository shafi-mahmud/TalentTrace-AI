# Submission walkthrough and acceptance — 26 October 2026

Scope: office branch `feature/office-20261026-acceptance`, implementation at
`34a0674`. This record does not merge the office branch into develop. Schema head:
`0017_booked_interview_email`, following `0016_submission_deletion`.

**Implemented** means inspected source. **Verified** below names its evidence
boundary; it does not imply complete BID acceptance. **Recommended** steps are
operator instructions, not claims that a demonstration has already happened.
The fourteen trainer areas below follow the owner's supplied checklist. No newly
located official trainer clarification document is claimed.

## Trainer acceptance matrix

| Area | Current implementation / entry point | Verified evidence and remaining boundary |
| --- | --- | --- |
| 1. JD refinement/chat | `RecruiterChat.tsx`; `POST /api/v1/recruiter-chat`; owned persisted conversations and revision checks | **PARTIAL**: provider/ownership/refinement automated coverage recorded in trainer status. Office browser restored a seeded draft; actual generation/refinement quality was not tested today. |
| 2. Job Reference | Saved job service, `GET /api/v1/jobs`, chat response and Home | **VERIFIED, bounded**: real office HTTP/PostgreSQL job creation/reload and browser reference display. Frontend never invents the reference. |
| 3. Multiplatform publishing | `PublishingReview.ts`; saved-draft review; `POST /api/v1/recruiter-chat/publish` | **PARTIAL**: real browser preview; destinations initially unchecked. Discord/Telegram transport tests mocked; LinkedIn/other are manual copy. No external post. Duplicate fencing is process-local. |
| 4. Strict CV/job isolation | Owned native intake, trusted imported-batch discovery and screening; exact job/batch/upload associations | **VERIFIED, bounded**: office two-job HTTP/PostgreSQL assertions reject cross-job acknowledgement/score/booking. Import/revision regressions recorded separately; no new provider-quality acceptance. |
| 5. CV notifications/analytics | `ApplicationNotifications.ts`; owned applications GET and explicit viewed POST | **VERIFIED, bounded**: browser New→Viewed plus refresh and separate job counts; 30-check office HTTP/database run. No inferred arrival dates or predictive analytics. |
| 6. Reviewed scheduling | `InterviewScheduling.ts`; saved-score selection, review, acknowledgement, booking | **VERIFIED**: actual office browser review/Confirm booking/refresh and independent SQL association checks. Score fixture deterministic. Email disabled, no live SMTP. |
| 7. Secure candidate access | `interview_access.py`; one-use invitation exchange, hashed scoped sessions/current window | **PARTIAL**: automated replay/owner/window/rotation checks and historical Cloud access. Invitation possession is not identity proof; cached media-token revocation remains limited. |
| 8. Recruiter suggestions | `copilot_live.py` trusted F4 bridge → graph → role projection and `InterviewCopilot.tsx` | **PARTIAL**: offline bridge/consent/projection tests; no complete current live STT→suggestion plus simultaneous candidate API/DOM exclusion acceptance. |
| 9. Simultaneous interviews | Scoped room grants and per-interview sources | **PARTIAL**: automated identity/isolation tests. Only one caption room per backend process; simultaneous live F4/F11 rooms unsupported. |
| 10. Online/physical face verification | Off-by-default synthetic enrollment/viva prototype, CPU YuNet/SFace adapter and encrypted reference workflow | **BLOCKED for real identity verification**: procedural-image comparisons prove computation only, not reliable identity/liveness. Persistent biometric vault is Linux-only; keep disabled on Windows. |
| 11. Local/API AI selection | Separate JD/CV selectors; fixed Ollama choices or configured Groq, no local→cloud fallback | **PARTIAL**: routing/consent/failure tests; office browser showed disabled-provider options and sanitized API rejection. No model inference today. |
| 12. Tab/fullscreen indicators | Optional consented coarse activity snapshot and expiry/withdrawal | **PARTIAL**: mocked DOM/auth/privacy tests; spoofable self-report, no reliable OS/F11 fullscreen or attention proof. |
| 13. Screen sharing | Explicit public SDK start/stop, screen video only, separate remote display | **PARTIAL**: mocked picker/denial/track/cleanup tests. Real browser picker and Cloud screen delivery unverified. No recording/audio capture. |
| 14. Home/navigation | `App.tsx`, `RecruiterHome.ts`, saved active-job state and shared styling | **VERIFIED, desktop bounded**: real office sign-in/Home/job navigation; TypeScript/build passed with Windows rename. Complete mobile visual walkthrough remains unverified. |

Evidence: [trainer status](trainer_feature_status_20261026.md),
[office transition](office_transition_20261026.md),
[F3/F4/F11 acceptance gates](office_f3_f4_f11_acceptance_preparation_20261026.md).
Private office reports remain ignored: `data/office-runtime-20261026/INTEGRATED_ACCEPTANCE.md`
and `BROWSER_BOOKING_PASS.md`. Their **30 HTTP/database checks** and **17 focused
frontend tests** are historical recorded results, not newly rerun counts.
Fourteen implemented areas do not mean fourteen complete acceptance passes.
Five areas (2, 4, 5, 6 and 14) have bounded real office HTTP/database/browser
evidence as specified above. The other nine retain partial or blocked acceptance;
this count is not a BID score or a claim of complete end-to-end verification.

## Final coordinated execution outcome

**Resource recovery: BLOCKED; sustained readiness not established.** The previous
run's manifest records `resource_limit`, without Join roles or media/caption timers.
It has no peak-memory journal. The new ignored test runner now records bounded
one-second memory samples, fixed startup phases and grouped process RSS without
command lines, credentials or browser contents. Fixture setup runs in a bounded
child process so its imports/pools exit before backend startup. This lifetime
change is offline-tested; its operational memory benefit remains unmeasured.

One new startup attempt stopped with **AttributeError before backend readiness**.
Its retained exception category has no stack, so the exact originating line is
**UNKNOWN**. A missing process-memory field case is now guarded and tested; that
does not prove it caused this attempt's failure. Future failures retain only
allowlisted component names and line numbers, never exception messages/locals.
No additional startup/Cloud attempt followed this failure.

Eight saved samples reached a minimum observed 2,098 MB available RAM, above the
unchanged 1,024 MB stop floor. WSL RSS reached 2,123 MB during Docker startup;
the two trial browser trees used about 1.3 GB combined and unrelated editors about
3.8 GB. Process RSS can double-count shared pages. No Whisper worker started, and
these measurements do not prove enough memory for two-role recognition. Unrelated
apps were neither terminated nor reconfigured. Docker/WSL limits were unchanged.

The Cloud dashboard showed Build, 404 of 5,000 included participant minutes,
2 GB of 50 GB included transfer and a $0.00 next invoice. This was a read-only
billing check, not a participant connection or guarantee about future billing.
**F3, F4, F11, simultaneous candidate exclusion, transcript persistence and
withdrawal: UNOBSERVED in this execution.** Historical Cloud media PASS remains
separate. The new database/complete fixture did not reach validation.

Cleanup confirmed Cloud unused, new disposable database stopped, both exact owned
browser roots absent and trial ports 5278/8078/55480 closed. Earlier data, evidence
and unrelated services were preserved. Private diagnostics remain Git-ignored.

Final focused checks: **38 Python harness/resource tests, 8 Node observer/SDK tests
and 17 frontend workflow tests passed**, zero failed/skipped in these selections.
These distinct suites are not added to historical broad-suite totals. Offline
migration inspection found exactly one head, `0017_booked_interview_email`, whose
parent is `0016_submission_deletion`; no preserved database was migrated. The
application/frontend source is unchanged since the previously passing Windows
TypeScript/build fix, so another expensive build was not required by this
documentation/ignored-harness increment. No new visual acceptance is claimed.

### Subsequent runtime recovery

The startup exception is now **CONFIRMED and fixed in the ignored harness**.
In `runner.py`, `run_trial()` assigned the SQL-readiness command's
`subprocess.CompletedProcess` to `probe` at line 227, replacing the resource
observer. Line 248 then called missing attribute `mark`. The later `error`/`close`
uses would also address the wrong object. Renaming the command result to
`database_probe` preserves the observer. Memory did not cause this AttributeError.
The previous UNKNOWN record above describes the evidence available at that time.

A regression executes the actual launcher through database readiness and the
migration-boundary observation with explicit offline doubles. Final focused
selection: **39 Python tests and 8 Node tests passed**, no failed/skipped cases.
Initial warnings from overly broad socket mocking in the new test were corrected;
the final Python run emitted no warnings. Application source was unchanged.

Exactly one fresh startup then reached **READY**: actual new disposable PostgreSQL
schema 0017, validated owned synthetic fixture, healthy backend/frontend proxy and
live independent watchdog. Seven minutes of ready-phase samples were retained.
Minimum observed available RAM was 1,768 MB, with 3,004 MB at the pre-stop snapshot.
The 1 GiB stop floor, consent, ownership and single-Join guards were unchanged.
Recruiter sign-in, saved-job display and saved schedule used the actual browser
and authenticated backend. No local recognition or media result is claimed.

**Live acceptance BLOCKED before any token/Join:** the candidate initially opened
the login root rather than `/interview-join`. A full-page navigation would trigger
the armed observer's existing fail-closed page-exit handler. No navigation bypass,
reload, server restart or second trial was attempted. F3/F4/F11, overlapping
candidate exclusion and persisted transcript remain **UNOBSERVED** in this run.
This is a test-entry lifecycle issue, not an established application media defect.

The initial watchdog receipt reported `cleanup_ok=false`; its detailed reason
was not retained. Independent reconciliation subsequently found all exact owned
roots and marked descendants absent, trial ports closed and the new database
stopped. Cloud was unused. Preserve this warning rather than retroactively
changing the initial receipt to PASS. The sanitized recovery outcome, memory
samples, startup health checks and reconciliation remain in the ignored trial
directory; earlier trials are unchanged.

**Recommended next action:** correct the isolated candidate initial-entry procedure
to load `/interview-join` before observer arming, and validate the pre-Join
navigation/cleanup lifecycle offline before requesting another live attempt.

## Recommended executable recruiter walkthrough

Prerequisite: authorized isolated synthetic runtime, exact source/schema verified,
private fictional login and approved synthetic files. Never reuse a stopped demo's
expired booking/invitation. Keep external providers, posting and SMTP disabled
unless separately authorized. Never use private evidence as Git demo content.

| Step and actual navigation | API / expected observation | Demo boundary |
| --- | --- | --- |
| Sign in → Home | `POST /api/v1/auth/login`, `GET /api/v1/jobs`; authenticated saved-job cards | Real auth; use private synthetic credentials only. |
| Home → Create Job through Chat → JD Assistant | `POST /api/v1/recruiter-chat`; show saved Job Reference/revision, then request a revision in the same conversation | Requires configured provider plus approved policy/RAG. With providers OFF show the unavailable state or restore a clearly labelled seeded draft; do not claim AI generation. |
| Candidate Screening → review criteria/weights | `PUT /api/v1/jobs/{job_id}/criteria`; explicitly confirm current revision | Revision changes require renewed review; retain same saved job identity. |
| JD → Review publishing / type `publish` | Review saved content and unchecked destinations; Discord/Telegram automatic only if configured, others manual | Stop before final external confirmation. Copying is not publishing. |
| Candidate Screening → native upload OR existing imported batch | Native CV upload; `GET /api/v1/jobs/{job_id}/imported-batches`; explicit screening POST under `/api/v1/cv-uploads/{job_reference}/{batch_id}/screen` | Synthetic files only; screening requires models. A deterministic fixture is a simulation, not inference. No automatic retry. |
| Saved results → Home counts/New/Viewed | Saved scores by exact job/batch; applications GET; explicit `/applications/viewed` POST | Verify refresh retains count and active job; switch jobs and check no mixed data. |
| Interview Scheduling → Load saved scores → eligible candidate → Review interview | `POST /api/v1/jobs/{job_id}/interviews` only after acknowledgement; review time/timezone/duration/application | Actual browser booking already passed. No need to create another booking merely to repeat proof. |
| Saved appointment → email review/status | `/appointment-email/preview`, explicit send, then status GET | Appointment confirmation is not joining access. Current office demo: Not configured. Mock SMTP acceptance is not mailbox delivery. |
| Open interview → invitation and candidate page | Owned invitation API, candidate one-use exchange; scoped role tokens only on authorized Join | Requires fresh open join window and separate profiles; do not rotate historical access or expose bearer. |
| Live interview → generated tracks | Public LiveKit SDK; both Connected, local audio/video published, remote audio/video received | Historical 25 October Cloud PASS; current combined trial pending. No physical media, retries or screen sharing. |
| Optional storage → captions → assistant consent | Independent storage, F4 caption and F11 consent; actual AudioWorklet/local Whisper; trusted events | Current combined live acceptance pending. No transcript insertion, cloud STT or fabricated captions. |
| Finish captions → load saved transcript → withdraw/Leave | Normal drain, stored roles/offsets; authorized retrieval; privacy withdrawal and cleanup | Do not infer persistence from visible captions. Do not infer candidate exclusion after suggestion cleanup. |
| Interview analysis → consolidated report/comparison | F5 analysis and validated F6 application assessment route; print control | F5 requires approved provider/reference setup and complete consented source. Disabled in this bounded trial. Offline connected integration is not today's live browser assessment. |
| Account → Logout | `POST /api/v1/auth/logout`; protected workspace inaccessible | No need to export cookies/session information. |

## Architecture and submission limits

Recruiter session → owned job/revision → batch/upload → saved score → immutable
interview selection snapshot. Candidate access uses the saved interview's scoped
invitation/session. Cloud transports generated media; consented AudioWorklet PCM
goes to **local** Faster-Whisper. Trusted server caption events feed optional F11.
Optional durable transcript/F5 analysis/F6 assessment retain source and ownership
checks. Appointment email and publishing are explicit, separate side effects.

Do not present a universal numeric ranking: excluded, uncertain, failed and
eligible-unscored outcomes remain distinct. N1's 20-input benchmark remains
PARTIAL (449.09 seconds; four numeric scores). N19 supports guarded exact-submission
maintenance only, not person-wide erasure. N21 baseline/isolated Docker tests do not
prove a full clean-machine Cloud/STT/evaluation deployment.

The existing UI is retained for the deadline. **Recommended, deferred polish**:
first complete desktop/mobile acceptance, then remove repeated instructional text
without removing consent or uncertainty disclosures; keep Home/navigation and
shared button/spacing styles. No sidebar/framework or half-finished redesign is
introduced by this checkpoint.
