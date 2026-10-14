# Bulk scheduling invitations

Implemented: authenticated job-level preview, explicit cohort confirmation and
read-only operation status. No browser-provided recipient list or provenance is
accepted. Migration 0009 adds only `bulk_scheduling_operations`; it is NOT applied
to the F4 demonstration database during implementation.

Routes under `/api/v1`:
- POST `/jobs/{job_id}/bulk-scheduling/preview`, body `{}`.
- POST `/jobs/{job_id}/bulk-scheduling/send`, body `{operation_id, confirmed: true}`.
- GET `/jobs/{job_id}/bulk-scheduling/operations/{operation_id}`.
Existing cookie authentication, mutation header and exact origin checks apply.
Preview/send require the current `X-TalentTrace-Job-Revision` header.

The backend considers at most 100 saved-result/application identities. Current
revision/scoring-version results are restored with the existing strict score
validator and checked against job identity/weights. Only numeric scored eligible
results qualify. Original contacts come only from the exact job/batch/upload ledger
and validated Forms provenance. Missing, invalid or ambiguous contacts, stale or
incomplete results, booked candidates and every previous invitation are excluded.
Recipient comparison follows the existing conservative case-insensitive allowlist
policy. Duplicate authoritative recipient mappings exclude all ambiguous sendable
candidates; booked/invited identities are not silently selected as a replacement.
Preview contains opaque candidate references and masked addresses, not raw contacts.

A durable UUID preview expires after ten minutes and fingerprints the complete
cohort, evidence, source mapping, job revision/weights and delivery configuration.
Confirmation recomputes it under the same recruiter row lock used by individual
invitation/booking paths. A changed preview is rejected. At most ten recipients
are permitted; larger sendable cohorts are shown but cannot be sent.

Admission commits `running` before delivery. Each recipient is rechecked before
using the existing individual email helper; its candidate token generation, hash,
seven-day expiry and durable delivery attempt are unchanged. Bulk attempt IDs are
reserved atomically with invitation records before SMTP, enabling read-only status
recovery without exposing tokens. No long transaction spans SMTP. A PostgreSQL partial unique index also permits only one running operation per job.
Another active bulk operation conflicts; replaying the same operation never sends again or revokes
previous links. Manual invitation races are serialized by the existing recruiter
lock and excluded/reused safely.

Accepted/failed/uncertain/skipped outcomes persist separately after each recipient.
Partial success is retained; no failed or uncertain send is automatically retried.
SMTP acceptance is not proof of mailbox delivery. Status GET checks durable attempt
IDs for recovery; a running operation with no progress for five minutes reports
review_required and blocks new bulk dispatch until operator reconciliation. There
is no background worker, automatic resume or administrative reconciliation UI.
A network timeout cannot be treated as proof that nothing was sent.

The recruiter UI provides preview, cohort confirmation, masked per-candidate
outcomes and Check saved operation status. It retains only the operation UUID in
session storage, checks saved status after reload, disables double submissions and
keeps the individual invitation feature as a fallback. Opening saved scores does
not import CVs, screen candidates or send email.

Verification: synthetic fake SMTP and disposable PostgreSQL cover ownership,
exclusions, stale previews, different tokens, concurrent/repeated confirmation and
partial failures/timeouts. Frontend guards/test coverage do not establish actual
browser or mailbox delivery. No live bulk dispatch occurred during implementation.

Recommended activation: approve backup/migration 0009, reload only F4, and review
any required restricted-gateway route update separately. Build verification uses a
separate runtime output directory, preserving the running tunnel build. The current
linked application address must be explicitly controlled and allowlisted before
sending. A two-recipient demo needs two distinct verified source contacts, normal
F4 screening, and separately approved inboxes; duplicate addresses cannot substitute.
