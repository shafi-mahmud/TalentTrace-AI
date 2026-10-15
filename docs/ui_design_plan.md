# Recruiter UI design plan

## Inspected architecture

React 19 with Vite and plain CSS; no routing or component library. `App` owns the
recruiter workspace, hash navigation and current job. `RecruiterSignIn` owns
authentication, session expiry and sign-out. Existing scheduling components reuse
the backend APIs. Candidate scheduling/join routes bypass the recruiter workspace.

## Implemented — Increment A

- One header: brand, the three existing navigation actions, and a right-aligned
  native account disclosure. The separate account bar is removed.
- Authentication stays in `RecruiterSignIn`; its account-control node is passed
  into `WorkspaceNavigation`. No duplicated session or sign-out implementation.
- The job selector appears only in Screening/Scheduling and recruiter interview
  context. Hiding it on JD Assistant does not clear or change the selected job.
- Shared color, spacing, typography, control and focus tokens establish the
  foundation. The header wraps into two rows on mobile; all navigation stays
  visible and keyboard accessible.
- No page restructuring, candidate route changes, API changes or dependencies.

## Planned — separate owner-reviewed increments

1. **B, JD Assistant:** conversation sidebar, chat transcript and composer layout;
   retain citations, human review and publishing confirmations.
2. **C, Screening:** requirements/upload task areas and outcome-focused results;
   preserve independent setup order, ranking, evidence and uncertain states.
3. **D, Scheduling:** candidate readiness, invitations, exclusions and booking
   history; preserve explicit send confirmation and operation reconciliation.
4. **E, remaining screens if needed:** audit login/candidate pages for consistent
   surfaces. Isolate any media/consent styling from functional controls and test
   it separately. LiveKit/Whisper behavior is outside this design increment.

## Verification and external-action safety

Use synthetic fixtures and mocked mutations in automated tests. Live visual
checks may navigate, open the account disclosure and load existing data read-only.
Never click live Publish, Send, Confirm, Screen, Generate or Book controls for
visual verification. Test their confirmations only with mocked transports.
The previous unintended synthetic Discord publication is not cleaned up here;
external deletion or modification needs separate explicit approval.

Review at 1366×768, 1920×1080 and 390px width at normal scale. Stop after each
increment, with tests/build and a local commit, for owner review.

### Increment A verification

165 frontend tests passed, including account disclosure, escaped identity,
pending/error states, explicit sign-out callback and navigation independence.
TypeScript and the production build passed; the existing LiveKit chunk-size
warning remains. Signed-in browser checks verified one header, no account bar,
desktop and mobile account access, Enter/Escape keyboard behavior, job continuity,
saved JD rendering and saved candidate results. All three viewport sizes used
scale 1 with no horizontal overflow. Live sign-out and all external actions were
left untouched; authentication transport is covered by mocked regression tests.
