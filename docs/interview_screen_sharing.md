# Optional interview screen sharing — 25 October 2026

Branch `feature/interview-screen-sharing`, based on candidate-access checkpoint
`2cd17b98c6e5cced7c918eb922e3e083ff068370`. Previous trainer features preserved.

## Implemented

Both authorized interview roles have Start sharing / Stop sharing controls, enabled
only while joined and not already busy/leaving. The installed LiveKit client 2.22.4
`setScreenShareEnabled` handles normal browser screen-selection permission. Nothing
captures or requests display permission on page load, join, render or polling.
Capture requests explicitly use `audio:false`.

`LiveInterviewPage.tsx` renders subscribed ScreenShare video in a separate Shared
screen section, with a separate local screen preview. Camera/microphone tracks
retain their existing containers. Screen unsubscription clears its display; native
local track end/unpublication updates the sharing state. Permission/publication
errors use fixed text and do not claim successful sharing.

The new `interviewScreenShare.ts` controller belongs to one room participant. It
serializes sharing operations, reads actual SDK track state and stops/detaches/
unpublishes local screen tracks on close. Native Stop updates state without a
new capture. Leave stops screen capture before waiting for the unchanged F4 drain.
Disconnect, revoked-access leave and interview-switch/unmount use the same cleanup.
A picker result arriving after close is immediately stopped/unpublished in the
old room, not allowed to update a replacement interview. Browser pickers cannot
necessarily be programmatically dismissed; cancel an outstanding picker when leaving.

## Grant and privacy boundary

Backend `services/livekit_interview.py` adds only `screen_share` to the existing
camera/microphone source allowlist for scoped recruiter/candidate grants. Screen
sharing audio remains excluded. Room identity, short token TTL, ownership and
candidate authorization are unchanged. Room creation/list/admin/recording/data
publishing/metadata permissions remain denied. Previously issued camera/microphone
only tokens cannot gain screen permission without a newly authorized grant.

The feature is not recording, screenshots, tab tracking, identity verification or
cheating detection. It transmits only the browser-selected screen video to the
existing authorized room after user action. F4 still reads Track.Source.Microphone,
never screen audio; F11 and all caption/storage consent paths remain unchanged.
Sharing does not accept caption, transcript or assistant consent automatically.

Existing revocation limits still apply: candidate access is periodically checked,
and cached self-hosted JWT revocation is not guaranteed. Do not interpret a local
cleanup test as proof of provider-side revocation or immediate remote termination.
No new external service or dependency was introduced.

## Verification

- Full frontend **319 passed**, zero failed/skipped. Focused sharing/finalization
  subset **9 passed** (included in full count).
- Tests use mocked participant/track lifecycle: no automatic capture, explicit
  start/stop with audio disabled, native Stop, denied permission, pending-picker
  completion after leave, duplicate-operation suppression, idempotent disconnect
  cleanup, separate remote-screen/camera containers and screen removal on disconnect.
- Backend access and real local SDK JWT-grant regressions: **27 passed**; provider
  calls mocked. Exact source permission assertions include screen video only.
- TypeScript and Vite production build passed; existing >500kB LiveInterviewPage
  warning remains. Git whitespace checks passed.
- Initial checks caught TypeScript strip-only constructor syntax and an incomplete
  older mocked participant. Constructor syntax and mocks were corrected before
  final passing checks. No production checks or permissions were bypassed.

Actual browser picker behavior, permission UX, native Stop timing, mobile/browser
support, screen readability and Cloud transport/revocation need separately approved
synthetic acceptance. No real display capture, microphone, Cloud call, token request,
recording, database migration, Docker build/start, merge or push occurred here.
