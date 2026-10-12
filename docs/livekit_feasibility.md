# LiveKit feasibility — 09 October 2026

## Historical feasibility assessment — 09 October 2026

LiveKit Cloud Build is a reasonable small one-to-one React/FastAPI audio/video
proof, separate from F2. Local configuration inspection found no complete
`LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` configuration. No project,
dependency, token endpoint, room, recording or interview schema was created.
Credential absence blocks the live proof, not F2 development.

**Update — 12 October 2026:** credentials became available and the bounded
recruiter-only Cloud proof is now implemented and live-verified with synthetic
media in two Edge sessions. See [Increment 2A](livekit_interview_proof.md) for current
security boundaries and unverified physical-device/production features. The
following capacity/setup analysis describes the earlier recommendation.

## Documented capacity and integration

Build is $0 with no credit card required. Current allowances include 5,000 WebRTC
participant-minutes/month, 50 GB downstream transfer and 100 concurrent participants.
Two people in a 20-minute interview consume approximately 40 participant-minutes;
125 such sessions exhaust the minute allowance before bandwidth and other use.
Check actual Cloud quota and bandwidth before a demonstration. Separate agent/STT
allowances are not evidence that transcription is enabled for this application.
Sources: [pricing](https://livekit.com/pricing),
[quotas](https://docs.livekit.io/deploy/admin/quotas-and-limits/).

React can use the browser `livekit-client` SDK with existing components; FastAPI
can issue tokens using `livekit-api`. These are future proof dependencies, not
installed here. No new framework is needed. Cloud's advertised sub-250ms media
delivery is a provider claim, not measured application latency or a guarantee.

## Exact setup and readiness checklist

1. An administrator creates a free Build project and checks region, allowances,
   data handling/retention terms and network access. Put its URL/key/secret only in
   ignored server configuration; never in `VITE_*`, frontend bundles or reports.
2. Implement an isolated authenticated backend join-token endpoint after approval.
   Authorize each participant for the room; opaque UUID room/participant identifiers
   are identifiers, not authorization. Use approximately five-minute tokens with
   only room-join/audio/video grants; no administrative/recording rights. Do not log
   tokens. Existing recruiter auth can protect a synthetic proof; real candidate
   invitation/ownership authorization remains a separate prerequisite.
3. Add a temporary two-browser React proof on unused local ports, with explicit
   camera/mic consent, mute/camera/leave controls and no recording/transcription.
   HTTPS or localhost is required for device permissions. Test actual microphone,
   camera, TURN/firewall fallback and remote media in two independent browsers.
4. Record only non-sensitive timing/pass-fail observations. Confirm tracks stop
   on leave and no room/token secrets or audio are retained. Preserve existing demo
   ports, DB and services; never use real candidate names or interview content.

Tokens expire for initial connection, not necessarily reconnect authorization.
Revocation must remove a participant and refuse future tokens; short expiry alone
does not remove an already connected user.
Source: [token generation](https://docs.livekit.io/home/server/generating-tokens).

## Privacy and future STT

Transport encryption is not equivalent to application-managed E2EE. E2EE requires
explicit enablement and secure key distribution. It prevents intermediaries without
keys from reading media; any future trusted STT participant needs the key to decrypt
audio, extending the trust boundary. It does not automatically establish consent,
legal compliance or retention controls. Future STT can receive room audio through an
authorized participant/agent, but no audio access, transcription or recording is
implemented in this increment.
Sources: [E2EE](https://docs.livekit.io/transport/encryption/),
[agent E2EE](https://docs.livekit.io/transport/encryption/agents/).

## Measurable proof acceptance — proposed, not measured

- Two synthetic participants join the same authorized room within five seconds.
- Ten minutes of two-way audio/video without disconnect; target observed one-way
  audio delay below 400ms, noting local measurement uncertainty and network conditions.
- Mute/camera controls visibly stop the corresponding remote media; leave stops
  local capture and removes the participant.
- Foreign-room access is denied, expired tokens cannot start a new join, and no
  secret is present in bundles/logs. No recording/transcript is produced.

Failure of security or reliable audio is a no-go for the reviewer demo. Keep a
manual Google Meet link as fallback. This is manual meeting use, not a claim that
Google Meet API integration or future STT access is implemented. Revisit LiveKit
after F2 live verification and secure project credentials are available.
