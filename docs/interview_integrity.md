# Optional interview activity and camera-verification boundary

26 October 2026; branch `feature/interview-integrity`, based on AI-provider
selection `d2cd8d4`. Previous trainer functionality is preserved.

## Implemented opt-in status

Candidate interview UI discloses sharing this page's visibility and fullscreen
status with the authorized recruiter. Checkbox starts unchecked; Share status is
an explicit action. Start, stop and pending-consent cleanup are separate from
camera, captions, transcript storage and F11 consent. Reconnection/context cleanup
clears the choice; no automatic re-consent or background retry is performed.

After versioned `attention-v1 / accept` consent succeeds, the observer reads only
`document.visibilityState`, `document.fullscreenEnabled` and
`document.fullscreenElement`. It sends the current snapshot on relevant events
and a ten-second heartbeat. One request is in flight with one latest pending
snapshot, preventing an unbounded event queue. No page URL/title, other tabs,
keys, clipboard, screenshots, camera pixels or window contents are inspected.

Page fullscreen entry/exit is an optional button action using the browser's normal
Fullscreen API. It is never forced. Unsupported browsers are labelled unavailable;
visibility/fullscreen unknowns remain unsupported. Browser-window F11 mode is not
reliably exposed by this API and is not claimed detectable. Hidden can mean a
background tab, minimized browser or other browser behavior, not misconduct.

Recruiters see **last reported** coarse values, or Not shared/unavailable. These
are self-reported browser states, not an attestation of attention, identity or
cheating. No score, adverse flag, automatic rejection, event count or activity
history is produced. Browser throttling can expire sharing; that is not cheating.

## Signaling, authorization and lifecycle

LiveKit data publishing stays denied. A small same-application authenticated HTTP
path avoids granting a general data channel:

- Candidate consent/report/withdraw routes are under `/interview-access/attention`.
  Existing HttpOnly candidate cookie, join window, current criteria/invitation and
  CSRF protection apply. Report accepts only run UUID and two enumerated states.
- Recruiter GET `/jobs/{job_id}/interviews/{interview_id}/attention` rechecks
  recruiter/job/interview ownership and current invitation expiry/revocation.
  The in-memory entry is bound to interview plus invitation/session identity.
  No candidate-only caller can read this recruiter projection.
- At most 64 entries per backend process. Only the current snapshot is held, with
  a 30-second timeout renewed by a valid report. Timers remove expired entries;
  no database, log/history table or durable telemetry is added.
- Withdrawal removes the run. Delayed reports cannot recreate it; an old withdrawal
  cannot remove a newer explicit consent run. Replacement candidate identity cannot
  inherit the prior snapshot. Independent interview entries do not share status.
- Local observation stops immediately on withdrawal, report failure or component
  disconnect/context cleanup. A consent response arriving after cleanup is withdrawn
  without installing listeners. Network loss can prevent remote withdrawal; the UI
  says stopped locally and the last record expires within 30 seconds. Hard browser
  termination relies on expiry. Recruiter polling is five seconds with a bounded
  request and can lag; no instantaneous distributed revocation guarantee is claimed.

No deployment flags were enabled and no runtime/Cloud session was started. This
store is deliberately process-local: multi-worker routing/restarts can make status
unavailable. It is not a reliable attendance record, audit ledger or proctoring
system. Clients can forge their own reports; authorization prevents cross-room
access but does not turn browser metadata into independently verified evidence.

## Camera / face verification: unsupported

Existing LiveKit camera controls and muted/active publication indicators remain
unchanged. Camera availability, video transmission and an invitation/session do
not prove candidate identity or even establish a usable face image.

No authoritative enrolled/reference face source, enrollment protocol or approved
biometric consent/retention contract was found in the inspected models, settings
and interview services. A CV photograph or arbitrary uploaded portrait would not
supply authoritative identity evidence. No image extraction, face embeddings,
matching, liveness decision or biometric storage was added.

Before any future face verification: clarify trainer scope and purpose, establish
an authorized reference/enrollment process, explicit candidate consent/manual
alternative, access/deletion/retention rules, accuracy/error/human-review policy
and resource requirements. Do not infer authorization for biometric matching from
ordinary camera permission or the new activity-sharing consent.

## Executed validation

- Focused backend activity and candidate access: **15 passed, zero failed/skipped**
  (25.64 s). Synthetic SQL/auth fixtures and local HTTP transport, no Cloud calls.
  Covers no-report-before-consent, strict metadata schema, owner isolation, candidate
  read denial, withdrawal/late updates, independent rooms, expiry and revocation.
- Full frontend: **326 passed, zero failed/skipped**. Synthetic DOM events verify
  visible/hidden, fullscreen/unsupported, bounded coalescing, failure cleanup and no
  automatic restart. Component test verifies unchecked consent/no initial API call
  and withdrawal of a late consent receipt after disconnect.
- TypeScript and production build passed. Existing >500kB LiveInterviewPage bundle
  warning remains. Whitespace checks passed. Existing page mocks were updated for
  the new child; fixture consent bodies were updated to the versioned contract.

No actual browser fullscreen/tab trial, remote-recruiter observation, reconnect
Cloud acceptance, real camera, biometric processing, recording, inference,
provider request, Docker operation, migration, merge or push occurred. Activity
functionality is implemented with synthetic acceptance; live behavior is unverified.
Camera readiness is existing functionality; biometric identity verification remains
blocked by missing requirements/reference/authorization infrastructure.
