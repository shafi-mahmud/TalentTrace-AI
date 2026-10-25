# Trainer-feature evaluation candidate — 26 October 2026

Source before this documentation: `6d9ce5ecb4dbe048b95280261bc495f40542f077`.
Base local develop: `cba35ab376ade05afb5a896bb64fba3bed5172c5`.
This is an **offline-tested source candidate**, not full live/trainer/BID acceptance.
The final documentation commit SHA is reported by Git, not embedded recursively here.

## Included history and exclusions

Analytics `cf647c5` and publishing `73513d5` were normally merged into trainer
integration `fd6a320` through `26b6ca2` and `3acede9`. Descendant commits are F11
`e947bdc`, candidate access `2cd17b9`, screen sharing `17775d6`, provider selection
`d2cd8d4` and optional integrity status `6d9ce5e`. All are in this ancestry.

Unapproved `feature/trainer-ui-finalization` / `f94c375` is excluded. No frozen F11,
LinkedIn or other experimental branch was newly merged. Earlier develop history
is preserved. Only a local fast-forward of develop is authorized by this task;
no remote publication or main update is performed.

## Concise feature matrix

| Trainer area | Implemented code | Automated evidence | Live/unsupported boundary |
| --- | --- | --- | --- |
| JD chat refinement / Job Reference | Saved owned jobs, refinement, reference/revision display | Recruiter-record, workflow and full frontend regressions | Actual generated content still requires human review and configured policy/RAG resources |
| Multi-platform publishing | Review/confirm destinations; Discord uses existing MCP adapter; opt-in Telegram channel uses Bot API; LinkedIn/other manual copy | Mocked confirmed receipt, failure/duplicate handling, auth and chat review | No real post made; no automatic LinkedIn capability; deduplication is process-local, not durable across restarts/workers |
| Job-isolated CV processing | Existing owned intake/screening; deduplicated native/imported application discovery | Counts/source/ownership cases and existing frontend validations | No new real CV parsing/provider-quality benchmark; application identity is not universal person identity |
| Reviewed scheduling / appointment email | Existing reviewed booking/contact/SMTP workflow from base | Existing frontend tests and historical Sprint 4 evidence | This run does not revalidate live SMTP or full booking-to-email PostgreSQL pipeline; no email sent |
| Candidate access | One-use invitations, hashed scoped sessions, current criteria/window checks; bounded exact-ready polling | Auth/replay/rotation/revocation and separate-client isolation regressions | Invitation possession is not identity verification; Leave permits reconnect; cached media JWT revocation limitations remain |
| F11 follow-up questions | Trusted caption bridge → model-free graph → recruiter-only optional suggestion; dismiss fixes late-poll race | Graph/bridge/API/consent/candidate projection/dismiss regressions | Fresh Cloud browser visibility, simultaneous candidate exclusion and terminal lifecycle observation remain unverified |
| Concurrent interviews | Independent room grants, cookie/profile and logical F11 run isolation | JWT/role/session/source isolation; rejecting second caption room leaves first intact | **One caption room per backend process**; multi-room F4/live F11 not implemented; no new simultaneous Cloud media trial |
| Camera / face verification | Existing camera readiness and publication controls | Mocked access/media lifecycle checks | No authoritative enrollment/reference, biometric consent/retention/error policy; **face matching unsupported** |
| Local/API AI choice | JD interpreter and generator route to allowlisted Ollama or configured Groq; explicit new-UI choice and cloud disclosure; conversation pin | Mocked local routing, schema/timeouts/no fallback, owner and pin tests | JD and CV have independent selectors; CV profile/matching both route explicitly and cloud requires transfer confirmation. No actual model quality/performance claim; legacy JD API behavior remains |
| Tab / page-fullscreen indicators | Optional candidate consent; scoped coarse current snapshot; expiry/withdrawal; recruiter-only last-reported view | Synthetic DOM, backend consent/auth/isolation/revocation/expiry and late-consent cleanup | Self-reported and spoofable; not cheating proof. Browser F11/window fullscreen not reliably detected; no activity history or browser surveillance |
| Screen sharing | Explicit SDK start/stop, screen video only, distinct remote display, late-picker cleanup | Mocked track/native-stop/denial/leave tests; scoped SDK grants | Real picker, browser/mobile support and Cloud delivery/revocation unverified; no recording or screen audio |
| Home / consistent interface | Existing approved navigation/Home and functional controls preserved | Full frontend rendering/workflow tests and production build | Unapproved UI pass excluded; no new desktop/390px browser visual acceptance |
| Counts / new applications / viewed | Received/new/viewed/available, source breakdown, All/New/Viewed, displayed-snapshot acknowledgement | Count/reconciliation/auth/late-arrival/filter tests | No reliable arrival dates, complete failure-history analytics, predictive metrics or automatic acknowledgement |

Automated cases use synthetic fixtures and mocked provider/media boundaries. SQL
doubles are not live PostgreSQL durability/concurrency proof. Existing historical
successes are not relabelled as today's physical acceptance.

## Defaults, privacy and audit

Ollama, LiveKit synthetic/local opt-in, AssemblyAI synthetic, F5 evaluation, F11
and live F11, transcript storage, reviewer confirmation and email default false.
Groq key and LiveKit credentials default absent. Compose's baseline disables its
optional services. No runtime configuration was enabled or service started.

New JD UI starts with no provider and requires confirmation for Groq processing.
The legacy JD API retains configured-Groq semantics; this is not universal transfer
consent enforcement. Local choice cannot fall back to cloud or silently switch an
existing conversation. Fixed loopback Ollama URLs/model IDs are server controlled.
Unavailable providers fail safely; actual API billing/quality was not checked.

Screen sharing and activity reporting require participant action/consent within
an authorized interview. Attention has no independent durable history and expires;
screen/audio capture is not initiated by this integration. Optional activity does
not enable LiveKit data grants. Candidate CV data was not used or transmitted.

Targeted introduced-object review found no high-confidence credential/private-key/
session-cookie pattern or known local DB-password match. No ignored data/artifact,
dependency, lockfile, Compose or migration changes are introduced relative to cba35ab.
This bounded audit is not an exhaustive guarantee against arbitrary private content.
Schema head remains existing `0017_booked_interview_email`; no database was touched.

## Minimal synthetic demonstration sequence (not executed here)

1. Use an approved isolated synthetic runtime, confirm source/schema/provider flags
   and sign in with its existing fictional recruiter. Open Home and select a saved
   job; retain its Job Reference across navigation.
2. Show received/new/viewed counts. Filter New, explicitly mark only shown entries,
   refresh and show Viewed. Explain that refreshing alone never acknowledges.
3. Open the saved JD. Type `publish` and review destinations. Show LinkedIn/manual
   copy versus configured Discord. Demonstrate receipts only with a labelled mocked
   provider fixture; do not click real Discord confirmation without separate approval.
4. Show JD AI choices/unavailable states without invoking a model. Explain both local
   stages, no fallback and the unchanged CV-screening provider boundary.
5. Open saved scheduling/history and explain candidate one-use access. For this
   offline candidate, use labelled fixtures/tests to show interview controls and
   recruiter-only F11 output, rather than creating a booking, room or invitation.
6. Show explicit screen-sharing and activity-consent controls using a mocked browser
   fixture, not real capture. Explain optionality, expiry and face-verification gap.

Any real Cloud/F4/F11, fullscreen/screen-capture, SMTP, model inference or external
publication trial needs separate authorization and resource/readiness checks.
No new full 20-CV, whole-candidate erasure, complete Docker-deployment or F6 physical
print/PDF acceptance is claimed by this trainer integration.

## Evidence details

See [functional integration](trainer_functional_integration.md),
[analytics](dashboard_application_analytics.md), [publishing](multiplatform_job_publishing.md),
[F11](f11_trainer_finalization.md), [access/concurrency](candidate_access_concurrency.md),
[screen sharing](interview_screen_sharing.md), [provider choice](jd_ai_provider_selection.md)
and [optional integrity](interview_integrity.md).

## Final offline regression results

One combined backend pass over recruiter records, notifications/counts, publishing,
JD/provider routing, access/room grants, captions, copilot graph/delivery/bridge,
transcript consent and activity privacy: **317 passed, 2 skipped**, 71.79 seconds.
Skips are the explicit disposable PostgreSQL notification gate and real local
Whisper-worker model gate. Neither is counted as passing. Provider/media transports
were mocked; no real inference, cloud connection or database acceptance was run.

Full frontend **326 passed, 0 failed/skipped**, 12.94 seconds. TypeScript and Vite
production build passed (existing >500kB LiveInterviewPage chunk warning). Git
whitespace checks passed. Default-field inspection confirmed optional integrations
OFF and credential defaults absent. Targeted audit scanned 75 introduced blob/commit
objects with no matching sensitive pattern/known local password.

Result: **offline integration PASS; live evaluation acceptance remains PARTIAL**.
Only documentation was added during this final consolidation; tested functionality
was not changed. Local develop is eligible for the requested history-preserving
fast-forward, without modifying main or any remote ref.


## Gap-closure extension

`feature/trainer-gap-closure-1` starts at this document's published-source successor
`7c2725e`. CV provider selection (`5127f7f`) and Telegram publishing are separate
implementation commits; develop and other feature branches are unchanged.
See [CV selection](cv_ai_provider_selection.md) and
[publishing capabilities](multiplatform_job_publishing.md) for configuration,
consent, provenance, failure handling and mocked evidence. This extension adds no
model-quality or live publishing acceptance claim, migration or dependency.

Gap-closure verification: 231 combined focused backend tests passed, one explicit
PostgreSQL gate skipped; 17 overlapping Telegram-focused tests passed afterward,
including added real-route authorization coverage. All 331 frontend tests and
TypeScript/production build passed. Models/providers were mocked throughout;
no Docker, Ollama, Cloud runtime or external publication was started. CV local-model
accuracy and actual Telegram channel delivery remain unverified.


## Isolated face-viva prototype

The later `feature/face-verification-viva` branch adds only an opt-in, RAM-only
synthetic-vector enrollment/comparison lifecycle and an unactivated optional
YuNet/SFace CPU adapter. See [face-viva status](face_verification_viva.md).
**Actual face-model use and physical-viva identity verification remain blocked**:
no approved local models/OpenCV/artificial face samples or real-biometric policy,
protected persistence and cross-session authority are provisioned. Numeric-vector
outcomes are simulations, not face-recognition accuracy or liveness acceptance.


Approved real CPU follow-up: see [YuNet/SFace readiness](face_cpu_readiness_20261026.md).
Official pinned models loaded; YuNet detected the procedural faces and SFace
extracted one valid 128-value feature. Both probes were quality-rejected; no valid
pairwise match/accuracy result exists. Production/on-site enrollment remains blocked
and the HTTP synthetic demonstration remains disabled by default.


Bounded SFace follow-up: [actual comparisons](face_matching_proof_20261026.md)
produced 0.99940291 for a +1-brightness variant and 0.90649607 for a separate
procedural design, with all unchanged gates passing. These demonstrate real
embedding/cosine computation; the high second score does not establish identity
discrimination. No real-world biometric accuracy or physical-viva acceptance claimed.
