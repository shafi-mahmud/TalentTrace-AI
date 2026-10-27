# Task 3 resume handover

Updated 27 October 2026 (Asia/Dhaka). This is a checkpoint, not completed F3 acceptance.

## Git and scope

Worktree: `D:\VS Code\TalentTrace-AI-office-20261026`.
Branch: `feature/office-20261026-acceptance`.
Pre-checkpoint HEAD: `9f075925498b600bc8c2b99cc85b90a3e2ae4efe`.
Use `git rev-parse HEAD` for the current exact checkpoint; the commit containing
this document preserves the changes below. Do not create another branch or modify
the original dirty checkout. No merge or push is authorized.

## IMPLEMENTED changes and complete checkpoint file inventory

| File | Purpose |
| --- | --- |
| backend/app/api/routers/jobs.py | Return and validate the saved conversation's pinned provider. |
| backend/app/services/score_records.py | Validate/expose existing stored AI provenance; reject inconsistent metadata; preserve scoring mathematics. |
| backend/tests/test_recruiter_records.py | Provider restoration, allowlist and sanitized failure coverage. |
| backend/tests/test_score_integration.py | Provider factory double, provenance reload/legacy/corruption and incomplete retry coverage. |
| frontend/src/api/jobs.ts | Validate restored provider identity. |
| frontend/src/api/savedScoreValidation.ts | Validate optional saved provenance. |
| frontend/src/api/scoring.ts | Strict provenance contract, including legacy absence. |
| frontend/src/components/CvIntake.tsx | Guided applicant review, explicit screening action, progressive disclosure and imported-context consent reset. |
| frontend/src/components/ImportedBatches.ts | Notify parent when imported batch context changes. |
| frontend/src/components/LiveInterviewPage.tsx | Show actual scheduled join window; clarify invitation action label. |
| frontend/src/components/ProviderSelection.ts | Default available Groq after authenticated discovery; respect explicit choice and pinned contexts. |
| frontend/src/components/RecruiterChat.tsx | Restore/pin original conversation provider and reset external consent. |
| frontend/src/components/RecruiterHome.ts | Five-stage journey and criteria-supported next action; remove duplicate CTA. |
| frontend/src/components/SavedScores.ts | Display stored provenance in saved results. |
| frontend/src/components/cvIntakePresentation.ts | Six-stage applicant workflow. |
| frontend/src/components/interviewTime.ts | Format existing ten-minute-before / duration-plus-fifteen join window. |
| frontend/src/components/scorePresentation.ts | Honest provider/model/consent rendering; unknown for legacy records. |
| frontend/src/components/screeningPresentation.ts | Include provenance in immediate screening results. |
| frontend/src/index.css | Responsive workflow grid. |
| frontend/src/types/screening.ts | Optional provenance type. |
| frontend/tests/interviewFinalization.test.ts | Real time helper in test harness; retain cleanup/failure coverage. |
| frontend/tests/interviewTime.test.ts | Join-window display coverage. |
| frontend/tests/providerSelection.test.ts | Default/pinned/explicit-choice/consent and provenance coverage. |
| frontend/tests/recruiterHome.test.ts | Guided next-action and navigation coverage. |
| docs/task3_resume_handover.md | Durable checkpoint and unfinished acceptance. |

Groq selection never checks external-processing consent. JD and CV permissions
remain separate. Imported-batch changes reset CV consent. No automatic provider
fallback or scoring-policy change was introduced. No schema migration was added.

## TESTED before the pause

Retained local outputs under ignored `data/groq-runtime-20261026/`:

- `task3-frontend-tests.txt`: 101 passed, zero failed/skipped.
- `task3-backend-tests.txt`: 56 passed, zero failed/skipped. These use offline
  service/session doubles; they are not PostgreSQL acceptance evidence.
- TypeScript and host/container production builds passed in the preceding task
  session; existing large LiveInterviewPage chunk warning remains.
- Earlier initial test invocations failed due to command paths and outdated
  provider-factory/incomplete-batch test expectations. Corrected focused runs
  above passed; do not add their counts repeatedly.
- Real authenticated browser checks observed Groq defaulting separately for new
  JD and CV workflows, both consent boxes unchecked, Home journey/next actions,
  saved actual Groq model provenance and an eligible saved synthetic score.

## PARTIAL / UNVERIFIED

At the pause, the normal scheduling form was reached using the existing genuinely
screened synthetic application. No booking was confirmed. Native datetime input
automation did not produce a review; do not treat this as a proven application
defect. The old private booking intent is expired and must not be submitted.

No Task 3 invitation was created/exchanged, no LiveKit token issued and no Cloud
Join or generated-media trial occurred. Previous historical Cloud successes and
failures belong to separate evidence; they do not prove this version's media.
Fresh booking/reload, invitation access, bidirectional media, controls and cleanup
remain unverified. Mobile visual acceptance and imported-batch consent reset still
need targeted browser verification. Do not repeat AI inference just to test UI.

## Runtime and private evidence

Application: <http://groq-20261026.localhost:5280/>.
Compose project: `tt-groq-55de9df40a4a`; PostgreSQL schema 0017 is preserved.
On resume all three containers were stopped; the existing database/backend/frontend
were started with the baseline Groq override. All became healthy. This operation
did not migrate, reseed or replace volumes. Baseline F3 remains disabled.

From the worktree root, normal safe startup (already configured/built machine):

```powershell
docker compose --env-file data/groq-runtime-20261026/compose.env -f compose.yaml -f compose.groq.yaml up -d --no-build --wait --wait-timeout 120
```

Do not use `down -v`, migrate or rerun provisioning. Private synthetic credentials
remain in ignored `LOGIN.json`; never print or stage them. The ignored
`task3-current.json` points to the preserved F3 preparation namespace containing
private Cloud configuration, temporary Compose override and expired booking intent.
Do not print resolved Compose configuration, credential files or invitation URLs.
No separate trial processes have been started in this resumed session.

The owner reconfirmed sufficient Build-plan free allowance and no paid risk on
27 October before any Cloud action. One synthetic-only trial remains bounded:
one Join per role, no retries, generated tracks only, target <=120 seconds media.
Keep captions, storage, evaluation, assistant, email and biometrics disabled.
After a trial, restore only the backend to the two-file baseline using
`up -d --no-deps --no-build --wait backend`; preserve the database and frontend.

## NEXT SAFE ACTION

Continue authenticated browser acceptance without model requests. Select the
existing Task 2 Synthetic Intake A saved candidate, verify it remains unbooked,
enter a new future Asia/Dhaka appointment and 15-minute duration, then review and
explicitly confirm through the UI. Refresh and verify the saved job/application
association. Only then enable the isolated private F3 override, create one fresh
invitation, use a separate candidate browser context, and perform the authorized
single generated-media trial if all safety checks pass. Stop on first failure;
record exact observed stages rather than infer ICE or publication success.
