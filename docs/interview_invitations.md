# F3 Increment 2B — two-role interview access

## Implemented

The recruiter opens a current owned schedule, generates an invitation and copies
the link. A candidate accepts it without recruiter login and uses the same media
page. Recruiter and candidate have distinct opaque identities in one interview
room. No email, recording, STT, calendar or new workflow is implemented.
The existing development-only LiveKit opt-in remains required: this is a synthetic
development demonstration, not approval for real candidate deployment.

Migration `0005_interview_invitations` stores one current invitation per interview,
SHA-256 invitation/session hashes, expiry and revocation. Random bearers contain
256 bits of entropy. Raw invitations are returned once, never recoverable from
storage; replacement invalidates old links/sessions. Recruiter ownership and
current approved criteria are checked. Candidate access also fails if the owner
is inactive, ownership changes or criteria become stale.

The invitation is carried in a URL **fragment**, never a query/path. The frontend
removes it from the current history entry and posts it only in the exchange body.
Explicit acceptance atomically claims the link under the job lock. Only one
browser can claim it; duplicates return 409. The browser receives an HttpOnly,
SameSite=Strict cookie scoped to `/api/v1/interview-access` (Secure outside local
development). Only its hash is stored. Reload/leave/rejoin use that session,
not repeated invitation exchange. A copied session cookie remains a bearer
credential: this does not establish a verified candidate identity.

Default invitation expiry is 48 hours, configurable 1–168 hours and capped at
the interview window end. **Recommended policy**, not a trainer-authored rule:
join from 10 minutes before the scheduled UTC start until 15 minutes after the
scheduled duration. Issued JWTs last at most 300 seconds, capped by the remaining
window and candidate invitation expiry. Clients receive only camera/microphone
publish and subscription grants for the authorized room. Tokens remain in memory.

Revocation persists first, then calls LiveKit Cloud `RemoveParticipant` with the
opaque candidate identity and explicit revocation cutoff. A failed Cloud call
returns sanitized 502: local access is revoked but disconnection is **not** claimed;
retry revocation before sharing a replacement. Rotation also requires successful
old-session removal. Candidate UI checks authorization every 15 seconds while
joined. Window checks block new backend tokens; UI leaves at window end. A JWT's
expiry is not a server-enforced maximum duration for an existing Cloud connection.
Deployment-wide session teardown at window end remains **Planned**.
See [LiveKit revocation](https://docs.livekit.io/frontends/reference/tokens-grants/).

### Security review boundary — 12 October 2026

- Expiry, stale criteria, changed ownership and an inactive recruiter deny new
  backend token issuance. They do **not** call Cloud removal automatically.
  Already connected participants, and SDK-refreshed reconnect tokens, are not
  forcibly revoked by these database checks. Client polling is best-effort,
  not a security boundary against a modified client.
- Explicit recruiter revocation commits the local deny first, then removes the
  candidate through Cloud with a cutoff. Success confirms removal; 502 means
  future backend access is blocked but active disconnection is unconfirmed.
  Rotation will not issue a replacement if old-session removal fails.
- Reconnect uses the same authorized candidate session/identity; it does not
  permit a second invitation claim. A stolen session cookie remains a bearer
  capability, and another tab sharing that cookie can replace the same participant.
- The 20/minute limiter applies to candidate exchange/token POSTs only, per
  process and observed client IP. Status GETs and recruiter invitation/token
  routes are not covered. Proxy/NAT sharing, distributed attackers and worker
  restarts limit this protection; production ingress limits remain required.
  Cookies are isolated by host/path, **not port**: use distinct trusted hosts or
  browser profiles when running unrelated local applications.

No critical source defect was identified in this focused review. This remains
a development-only synthetic feature; it is not approved for real candidate use.

Mutation verification/origin checks protect exchange/token APIs. Bounded per-IP
hash buckets limit exchange/token attempts to 20 per minute per process; distributed
limiting, HTTPS deployment, security headers and abuse monitoring remain required
before real candidate use. Do not log bodies, cookies, JWTs or copied links.
Share links through a trusted channel; no delivery service is implemented.

## Verified — 12 October 2026

A **new disposable** localhost PostgreSQL/pgvector database migrated to 0005.
Real HTTP tests verified schedule association, foreign-owner denial, hash-only
storage, distinct signed grants, reconnect, stale criteria, expiry/window rejection
and revocation. Migration downgrade/re-upgrade and FK/uniqueness checks passed.
Simultaneous claims returned exactly 200/409. The live check found a SQLAlchemy
identity-map race; refreshing the invitation after the parent lock fixed it.
A focused regression models the stale cache; the real concurrent check then passed.
Live Cloud participant revocation returned 200.

Two Edge tabs used recruiter and candidate roles through the actual API/Cloud path.
The candidate invitation was accepted, synthetic remote video decoded and remote
audio played. Mute/camera state reached the peer. Candidate leave/reload/rejoin
worked. Revocation disconnected the candidate and subsequent join failed safely.
Browser tabs share an Edge profile; anonymous candidate authorization was also
verified with independent cookie jars in the real API check. This is not a claim
of isolated browser profiles or physical-device capture.

**Historical automated-agent boundary:** the earlier checks did not capture
physical devices. The user-observed physical check below supersedes that gap;
measured latency, network-loss reconnect and cross-network operation remain
unverified. No real candidate data or Groq/Discord calls were used in those checks.

Final automated checks: backend **1,051 passed, 6 skipped**; frontend **120 passed**;
production build and `git diff --check` passed. The SDK chunk-size warning remains
non-blocking. These counts are automated results, separate from the live checks.

## Manual verification

1. Apply 0005 only to an approved isolated migrated database; provision a synthetic
   recruiter, approved job and eligible scheduled interview within the join window.
2. Configure ignored server LiveKit credentials and opt-in. Run frontend/backend
   on unused matching ports. Sign in as owner, open schedule, generate/copy link.
3. In a separate candidate browser profile open link, accept once and confirm the
   synthetic test. Join both roles. Use generated media first.
4. With headphones and privacy-safe surroundings, disable generated media on both
   sides, allow camera/mic, verify physical remote audio/video, mute/camera, leave,
   reload and rejoin. Do not equate generated-media success with physical success.
5. Revoke as recruiter: candidate disconnects and cannot rejoin. Replacement uses a
   new identity. Test expired link/window, stale criteria and foreign recruiter denial.
   Leave both clients and remove only the disposable resources.

## User-observed physical-media verification — 12 October 2026

The project owner reported a manual Edge test in the separate disposable
physical-device environment: recruiter and candidate joined, physical webcam
and microphone capture and remote audio/video worked, mute/camera controls
worked, the candidate rejoined, and recruiter revocation blocked candidate access.

This is **user-observed verification**, not an automated result or an independently
observed agent test. It closes the local F3 physical-media demonstration milestone.
It does not establish cross-network operation, measured latency, long-duration
reliability, forced disconnection timing, expired-token behavior, or production
readiness. The reported blocked access must not be expanded into claims about
all cached Cloud tokens or active-participant removal. No recording or STT was
implemented by this test. Existing authorization boundaries above still apply.
