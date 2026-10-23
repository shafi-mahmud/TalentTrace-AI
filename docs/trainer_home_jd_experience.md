# Trainer Home and conversational JD sprint

## Increment A: implemented recruiter Home

The default recruiter route and `#home` show jobs from the existing authenticated
`GET /api/v1/jobs`. Cards show the actual title, Job Reference, revision, saved
criteria-confirmation status and active selection. No candidate/interview counters
are inferred. Loading, empty and failed requests have distinct states.

Home uses the existing account menu and design tokens, with a responsive card
grid. It can select a job, continue its screening, open scheduling, or start a new
chat. Starting from Home resets the chat component explicitly. Pending chat work
disables job-changing Home actions. Same-revision local criteria edits are retained
when opening a job from Home. Existing per-recruiter active-job restoration remains;
job contents are reloaded from the authorized server, not browser storage.

Candidate invitation/scheduling/privacy routes remain outside recruiter navigation.
No authentication, provider, database-schema or production activation changes.

Validation results are recorded after the focused checks. Browser/provider
acceptance is separate from synthetic rendering, callbacks and reducer tests.

Increment A validation: all 260 frontend tests passed; 16 backend authenticated
workspace tests passed; production TypeScript and Vite build passed (existing
large LiveKit chunk warning). A final 16-test Home/shell/chat-state subset also
passed after locking job changes during uncertain delivery. The initial Home
error test expected the wrong existing safe message; corrected before commit.
No live browser, model, database or protected runtime was used.

## Increment B: implemented saved identity and refinement

Generated assistant messages preserve the server's `job_reference` and
`job_revision`. The card displays the Job Reference, revision, explicit saved
status and a copy button. The internal UUID appears separately in a disclosure.
Legacy replies without persisted identity show an unavailable message rather
than inventing a reference or asserting a successful save.

Use Home's **Refine saved JD**, or select the saved job and open JD Assistant.
The existing owned conversation is loaded through its normal GET endpoint.
Restoration failure blocks sending; it never silently starts another job.
Conversations still expire under the existing server policy (30-minute window).
No automatic conversation renewal, request replay or new agent was added.

**Revise draft** focuses an empty composer; describe the requested difference
instead of re-sending the original instruction. The composer identifies the saved
job/revision and sends the next instruction with the same conversation ID.
Successful revision replaces that job's working criteria, clears local approval,
and carries its server identity into Candidate Screening. Existing `persist_chat`
already increments the job revision and clears its confirmed snapshot. Existing
custom weights are retained locally; the server remains authoritative.
Older revision cards have disabled actions. Another job's working draft is retained.
Failed/uncertain sends retain the draft and instruction with explicit retry rules;
no automatic provider request or retry is introduced. Pending/uncertain delivery
locks Home job changes until the conversation is finished or reconciled.

Normal flow: sign in â†’ Home â†’ Create Job through Chat â†’ send role requirements â†’
read/copy the returned Job Reference â†’ Revise draft â†’ send a specific change â†’
see the same reference and higher revision â†’ Review screening criteria for this
job â†’ review and reconfirm. Existing saved jobs can start at Refine saved JD.

Offline verification uses actual React component callbacks/reducers with mocked
API boundaries and the real authenticated backend routes/persistence services
with the existing transactional SQL double. No real model or database was used.
Final validation counts and known limits are recorded below.

Final Increment B validation:

- All **267 frontend tests passed**, zero failed/skipped, including real component
  event/hook execution, workspace navigation/reload, identity display/copy,
  same-conversation revision, criteria reconfirmation, cross-job preservation,
  uncertain delivery and failed restoration. Test APIs/models are doubles.
- Focused backend: **134 passed**, zero failed/skipped, covering existing
  interpreter/grounding/security/persistence behavior plus the new same-job
  authenticated refinement scenario. Actual SQL execution uses the existing
  transactional double, not PostgreSQL. Increment A's 16 backend checks overlap
  this invocation; do not add their counts.
- Production application/configuration TypeScript and Vite build passed. The
  existing >500 kB LiveKit chunk warning remains. No browser visual/physical
  media or real-provider demonstration was performed or claimed.
- Initial harness imports, one legacy UI wording expectation, the new semantic
  double's experience evidence, ORM-instance comparison and raw JSON-null
  comparison required corrections. Final runs above passed without weakening
  production validation. Saved replies were compared through the existing typed
  response model, because persisted JSON intentionally omits optional nulls.
- Diff checks and targeted sensitive-payload scans passed. Existing dependencies
  were reused via an ignored worktree-local junction; no packages installed.

Remaining: trainer browser review of the responsive layout and an independently
approved model-backed refinement walkthrough. Persisted conversations retain the
existing expiry/turn limits; renewing refinement after expiry while preserving
job identity is not implemented. No unrelated trainer suggestion is claimed done.
