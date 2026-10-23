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
