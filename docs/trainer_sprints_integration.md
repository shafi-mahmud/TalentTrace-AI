# Trainer sprints 1–3 integration acceptance

## Implemented integration

Baseline: `49961fc74c48c38e0cb16c5e12b10ba6c2d7593d`.
The integration branch first fast-forwarded to dashboard `9ad003a`, which already
contains Home/JD `2660232`, `67e88ae` and notification `aeea7ee`. Scheduling
`b67dde1` is the second merge parent. No commits were duplicated or rewritten.
Git automatically merged the independent CSS additions; there were no conflicts.

Browser inspection found missing padding on Home's new cards. Two shared-style
rules now pad the welcome, selected-job and saved-job cards, and avoid a redundant
nested border around application analytics. No navigation or business semantics
were changed during integration.

## Automated verification

- All **285 frontend Node tests passed**, zero failed/skipped.
- Selected backend suites: **194 passed**, initially 3 opt-in PostgreSQL cases
  skipped. All three were subsequently enabled on fresh disposable resources and
  **passed**. Thus **197 distinct backend cases passed**, zero failures or
  outstanding skips within the selected suites; the entire backend suite was not
  run. Counts do not add repeated cases or assertions.
- Covered: Home/workspace/login, JD refinement and saved identity, job isolation,
  notifications and snapshot acknowledgement, CV upload/import/bridge, booking,
  invitation authentication, timezone/overlap, F2 scoring and eligibility ranking.
- TypeScript app/node checks, production Vite build and Git whitespace checks
  passed. The existing large LiveKit chunk warning remains.

The notification PostgreSQL harness still verifies the 0011 down/up sequence on
its own disposable database, then upgrades that fresh database to current head
`0016_submission_deletion` before exercising current import models. The previous
0011-only setup omitted later contact columns.

The bridge PostgreSQL harness now refuses the old hardcoded shared container. Its
opt-in requires `F4_BRIDGE_TEST_CONTAINER`, prefix `tt-trainer-tests-`, label
`talenttrace.test-only=trainer-sprints`, volume-only mounts, one loopback database
port and matching `F4_BRIDGE_TEST_PORT`. It creates a unique database and migrates
only that database. External-intake testing used a separately created database in
the same new container, through `EXTERNAL_INTAKE_TEST_DATABASE_URL`. Notification
testing created its own fresh container. No protected database was reused.

The fresh test resources used the already installed pgvector/PostgreSQL image,
without pulling images or mounting host configuration/candidate data. Only
fictional records were inserted. The harnesses stopped their test-owned
containers on completion. No deletion acceptance or external provider was used.

## Browser-verified with SIMULATED API responses

The actual integrated production frontend build was served on isolated loopback
port 5217. A small local, in-memory HTTP double supplied fictional responses; a
visible banner labelled every page **SIMULATED API**. This is real frontend/browser
verification, not real-provider or deployed-backend acceptance. Neither preserved
LiveKit nor protected application origins were contacted.

| Journey | Observed result |
| --- | --- |
| Login → Home | Fictional sign-in opened the real Home UI and saved-job controls. Backend auth/ownership is covered separately by automated tests. |
| Home → Create Job → JD → Refine → Screening | Reference stayed `TT-JOB-0000000000000003`; revision advanced 1 → 2; latest criteria opened in Screening and required review. Responses were deterministic doubles, not model generations. |
| Job A notifications | Received 3: native 2, trusted import 1. Explicit acknowledgement changed new 3 → 0; refresh retained the result. |
| Switch to Job B | Received/new 1/1 and Job B reference replaced Job A's 3/0; no mixed counts. |
| Screening → eligible candidate → Scheduling | Saved eligible-but-unscored evidence showed its warning; candidate selection navigated to the correct job. |
| Review → Confirm → saved schedule | Review required unscored acknowledgement and separate final confirmation, showing correct job/application, 15:00–16:00 Asia/Dhaka. One simulated booking was saved and remained readable after reloading/navigation. No invitation/email was generated. |
| Navigation/reload | Home, JD, Screening and Scheduling retained the selected job; restoring the saved JD showed the same reference/revision history. |
| Loading/error/empty | Delayed refresh displayed updating/stale status and disabled acknowledgement. Simulated 503 retained labelled stale counts; successful empty response displayed zeros and the empty message. |

Desktop 1440×1000 and mobile 390×844 were visually inspected. Home cards, navigation,
metrics, source bars, list and acknowledgement controls were inspected after the
padding correction. JD and saved schedule layouts were also checked at mobile
width. DOM width checks found no horizontal overflow in Home, JD, Screening or
Scheduling. Labels allowed operating chat, native date/time, duration, timezone
and acknowledgements. This is not a complete accessibility audit. The browser
tool needed a native keyboard event after date filling to retain the date; the
reviewed appointment used November 25, 2026, only in simulated memory.

Sanitized screenshots are retained locally in ignored `data/validation/`:
`home-desktop.jpg`, `home-mobile.jpg`, `jd-mobile.jpg`, `schedule-mobile.jpg`, and
`home-error.jpg`. No screenshot, generated evidence, credential or personal record
is committed. Logs and the local simulation scripts remain ignored as well.

## Remaining limitations and recommended next work

- Recruiter-booked joining email still needs a reviewed recipient/capability and
  durable send-attempt workflow; candidate self-scheduling remains distinct.
- Accurate chronological native-arrival history and complete screening-failure
  analytics remain unavailable in existing persistent data.
- The narrow table heading wraps at mobile width; no blocked controls or overflow
  were observed. The scheduling button also briefly uses its existing saving text
  while the initial saved-interview list loads.
- Real SMTP/inbox delivery, model quality, live CV screening, media and production
  deployment were not tested. Docker LiveKit remains blocked; F11 stays frozen.

Recommended next trainer increment: reviewed invitation delivery for an already
booked recruiter appointment, with fake-transport acceptance first. Do not treat
these simulated browser journeys as proof of real email or provider operation.

Existing feature worktrees, original uncommitted configuration, main and remote
develop are preserved. Local develop may be fast-forwarded only after this merge
is committed and its clean baseline is rechecked. No push is authorized here.
