# F3 Increment 2A — recruiter-controlled LiveKit proof

## Implemented

The owner opens a current scheduled interview's **Open synthetic interview proof**
action. Two browser sessions, signed in as the same owning recruiter, choose slots
A/B and explicitly confirm isolated synthetic testing. The React page supports
join, local/remote video, microphone mute, camera toggle, remote mute indicators,
remote audio playback recovery, leave and navigation cleanup. Existing JD/CV
workspaces stay mounted and preserve in-memory state while this page is open.
The LiveKit client is loaded lazily; no additional React framework is introduced.

Generated synthetic video/audio is the default, avoiding capture of office devices.
Optional device mode asks the browser for camera/microphone permission. Synthetic
tracks travel through the real LiveKit transport, not a mocked room or fake result.
No recording, transcription, calendar, email or publishing is implemented.

## Security boundary

`POST /api/v1/jobs/{job_id}/interviews/{interview_id}/livekit-token` requires the
existing recruiter authentication, mutation header and job/interview ownership.
Stale/unapproved job criteria fail closed. Requests accept only A/B and an explicit
synthetic confirmation; arbitrary room, identity, provider or credential fields
are forbidden. Development environment and `LIVEKIT_SYNTHETIC_DEMO_ENABLED=true`
are both required; the opt-in flag defaults false. This is a deployment safety
gate and user acknowledgement, not automatic proof that database data is synthetic.

Server-side `livekit-api` signs a five-minute JWT. HMAC-derived room/participant
identifiers disclose no recruiter/job/candidate IDs. The two identities are stable
for this interview; reusing a slot can replace that test participant, so use A/B
on separate sessions. Grants permit only scoped room join, camera/microphone publish
and subscription. Admin, room-list/create/record, screen sharing, own metadata and
data publishing are not granted. No token, room record or media is persisted by
TalentTrace. API responses are no-store; tokens remain transient in browser/SDK
memory, not URLs, React conversation history or browser storage. SDK logs are
disabled and application errors are fixed/sanitized.

Credentials stay in ignored server configuration. Only a validated `wss://...livekit.cloud`
URL and the necessary bearer token reach the client. Server signing credentials
are not shipped as frontend configuration. LiveKit JWTs necessarily include the
SDK's issuer key identifier; the signing secret is never sent to the browser.

The proof may join before the appointment time for synthetic testing. Production
join windows, candidate invitations/authorization, revocation/rate-limit governance
and privacy/retention controls remain planned. Token expiry controls initial join,
not an already connected participant's lifetime or all reconnect behavior.
Transport encryption is not E2EE: no E2EE key distribution is implemented and
the Cloud media service is part of the trust boundary.
Sources: [LiveKit token grants](https://docs.livekit.io/home/server/generating-tokens),
[encryption](https://docs.livekit.io/transport/encryption/).

## Verified — 12 October 2026

A fresh disposable localhost-only PostgreSQL database reached migration 0004.
An administrator-provisioned synthetic account, validated synthetic screening
fixture and actual schedule-create API produced the owning interview. No office
database was migrated and no real candidate data was used.

Real API signing verified ownership rejection (404), no-store responses, 300-second
claims and two distinct opaque identities sharing one room. Backend unit tests
also cover exact SDK grants, disabled/production/missing configuration, stale
interviews, strict confirmation and sanitized signer failures. They make no Cloud
calls and are distinct from the following live proof.

Two independent **Edge browser sessions** joined the actual LiveKit Cloud room.
Both reported one remote participant, decoded remote synthetic video and active
remote audio playback. Microphone mute/camera off reached the peer; unmute/on
restored peer state. Back navigation and explicit leave removed media elements
and the other client observed participant departure. No physical device data was
captured. An in-app-browser attempt disconnected during connection; its cause is
unconfirmed, and cross-browser compatibility is not claimed.

Physical camera/microphone, perceived audio quality, measured latency, long-duration
reliability, network-loss/reconnect and live expiry/revocation remain **Unverified**.
This is a synthetic A/V transport proof, not a production candidate interview system.

## Manual setup/verification

1. Install pinned backend requirements and `pnpm install` in a separate development
   checkout. Configure ignored root `.env` with LiveKit credentials, development
   environment, opt-in flag and an isolated migrated PostgreSQL database.
   Settings reads `.env`, not Windows `.env.txt`; the local `.env.txt` was preserved
   and explicitly read only by the temporary verification launcher.
2. Use matching backend/frontend ports and proxy/trusted origin. Sign in as the
   interview owner in two browsers; open the same current scheduled interview.
3. Choose A/B, keep generated media enabled, confirm synthetic testing and join.
   Verify remote video/audio, mute/camera peer indicators, leave/back cleanup and
   foreign-owner denial. Do not use real candidate data or enable recording.
4. Leave both sessions before shutting down the isolated runtime. Candidate public
   joins must wait for an approved invitation/authorization design. A manual Google
   Meet link remains a separate fallback; no Meet integration is claimed here.
