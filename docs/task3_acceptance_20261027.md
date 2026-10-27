# Task 3 recruiter workflow and F3 acceptance — 27 October 2026

## Result

| Boundary | Result and actual evidence |
| --- | --- |
| JD/CV provider defaults | PASS: authenticated discovery reported available Groq; both real browser selectors selected it without checking either external-processing consent box. No new inference was requested. |
| Saved conversation | PASS: Home's Refine saved JD restored the same saved Job Reference/revision, pinned Groq and left refinement consent unchecked. |
| Guided workflow | PASS for inspected Home/applicant views: five-stage Home journey, criteria-supported next action, six-stage applicant review, explicit screening/scheduling actions and progressive evidence disclosure. |
| Saved-score provenance | PASS: real authenticated API and browser loaded the existing genuinely Groq-screened synthetic result and its stored provider/model/consent metadata. Legacy absence remains explicitly unknown. |
| Imported-context consent | PASS: real discovery completion and explicit batch selection each cleared previously checked CV consent. Neither action ran a model. |
| Responsive layout | PASS for the inspected Home/applicant views at desktop and a 390-pixel viewport; no horizontal document overflow. This does not certify every application page/breakpoint. |
| Scheduling | PASS: existing eligible application selected from saved scores; owner entered the native datetime control; browser review and explicit confirmation created one booking; refresh preserved its job, candidate, revision and start/end. Read-only database verification confirmed ownership and schema 0017. |
| Candidate invitation | PASS: one new invitation, initially unclaimed/unrevoked, associated with that booking. Separate Chrome context on a fresh local hostname accepted it once; fragment was removed. Candidate root showed recruiter sign-in, not recruiter data. |
| F3 Cloud media | PASS: normal application in Edge and Chrome, one Join per role; both showed Connected with one remote participant and no UI errors. Local video and remote audio/video elements had readyState 4 and were playing; remote video width was 480 pixels. Recruiter remote media time advanced beyond 25 seconds. |
| Media controls/cleanup | PASS for recruiter mute/camera-off propagation and both normal Leaves. Candidate mute propagated; candidate camera-off remote propagation was UNOBSERVED before departure. Both ended Left interview, zero participants and zero audio/video elements. |
| Email, F4, F5/F6 inference, F11 | Not exercised; disabled. Database contained zero booked-email attempts. No physical devices, recording, publishing or extra model request. |

The saved appointment was **27 October 2026, 08:40–08:55 Asia/Dhaka**, 15 minutes.
Its existing business-rule join window was **08:30–09:10 Asia/Dhaka**. It must not
be reused for another acceptance attempt. The invitation is now claimed.

## Evidence and limits

The owner freshly confirmed sufficient free Build allowance and no paid risk.
The complete interval from recruiter Join click through both Leave clicks was
**61,901 ms**, below the 120-second bound. Application Connected is set only
after Room.connect and both synthetic publication promises resolve; attached
remote elements come from the SDK subscription handler. These are actual browser
observations, not mocked API responses or inserted transcript events.

No separate SDK observer, internal peer-connection inspection, ICE trace, raw
WebSocket payload, media recording or Cloud billing measurement was collected.
No server-side signaling timeline is available for independent correlation; the
frontend access-log extraction yielded no matching records. Do not turn that
absence into a networking conclusion. This Cloud PASS does not explain earlier
self-hosted InternalError failures or certify future Cloud quota/configuration.
Physical-media, long-duration, public deployment, F4/STT and F11 remain separate.

Private evidence is ignored under `data/groq-runtime-20261026/`; `task3-current.json`
locates this trial namespace. It contains `task3-acceptance.json`, booking reload
and mobile screenshots, private invitation/configuration and sanitized HTTP-count
availability. Never commit those files. `home-mobile.png` was captured before a
navigation settled and shows applicants; use `home-mobile-confirmed.png` for Home.

## Focused validation

- Retained pre-pause outputs: 101 frontend and 56 backend tests passed, zero
  failed/skipped. Backend coverage uses transactional session/service doubles;
  it is not itself live PostgreSQL evidence.
- Resumed scope: 20 frontend tests passed, zero failed/skipped, across provider,
  imported-batch and time suites. Nineteen overlap the earlier run; one new test
  covers real consent-reset handlers and suppression of stale-job responses.
  The union is **102 frontend tests**, not 121. No broad backend suite repeated.
- TypeScript and production Vite build passed again. The existing >500 kB
  LiveInterviewPage chunk warning remains. Deployed frontend asset names match
  this build; deployed changed backend module hashes match the worktree.
- Real authenticated HTTP/browser/PostgreSQL checks verified provider availability,
  persisted score metadata, current ownership/revision, exactly one new booking
  and invitation, and unchanged migration head `0017_booked_interview_email`.
- No new production defect was demonstrated during resumed acceptance. Native
  date-input automation required owner assistance; it was not an application fix.

## Runtime and continuation

Application: <http://groq-20261026.localhost:5280/>. Existing Compose project,
database and volumes are preserved. Only its backend was temporarily recreated
with the ignored F3 override; after both Leaves it was restored to baseline.
It is healthy, F3 disabled and Cloud credentials absent. Frontend and database
remain healthy. Trial candidate/review tabs were closed; no independent test
server or container remains. The normal recruiter app remains available.

```powershell
docker compose --env-file data/groq-runtime-20261026/compose.env -f compose.yaml -f compose.groq.yaml up -d --no-build --wait --wait-timeout 120
```

This starts existing built/configured services, without migration or provisioning.
See [the durable handover](task3_resume_handover.md) for the full source inventory.
No merge or push was performed. A further media test requires a new valid booking,
invitation and scoped authorization; do not reuse this consumed acceptance.
