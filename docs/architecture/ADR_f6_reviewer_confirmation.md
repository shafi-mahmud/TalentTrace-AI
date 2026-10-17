# ADR — F6 reviewer confirmation

Status: implemented for opt-in synthetic development, 17 October 2026.
Parent: `5ef7e22317174b4cff8c948102b26215e5cee349`.

## Decision and alternatives

Persist one current versioned human confirmation per exact job/batch/upload.
F2 is weighted CV requirement coverage; F5 is advisory qualitative interpretation.
Neither model represents an authenticated human judgment. `unscored_confirmed`
means permission to schedule an unscored application, not suitability. Reusing it,
chat state, F2 payloads or F5 results would conflate ownership/lifecycles. A browser-
only acknowledgment cannot survive reload with trustworthy reviewer attribution.
A new table is justified for durable confirmation; full judgment history is not.

No hiring decision, ranking, numeric combination or model inference is added.
Three positions are explicit reviewer choices: alignment within reviewed scope,
mixed evidence requiring review, and insufficient evidence to form a position.
Rationale is typed reason codes plus validated requirement/evidence IDs. There is
no free-text rationale, stored transcript quote, CV copy, candidate name/email or
copied criterion description. Reviewer identity comes only from authentication.

## Evidence, transactions and validation

The existing consolidated report remains the evidence boundary. Confirmation
rebuilds it in the mutation transaction, retaining job then interview locks before
locking the confirmation. The job lock serializes simultaneous initial inserts;
a unique application key and expected version prevent lost updates. Existing
mutation header/origin protections apply. Client evidence tokens must match a
fresh canonical digest; they are expectations, never authorization credentials.

Stored source metadata consists of criteria/weights-in-CV digests, scoring/source
version and, when applicable, operation/input/result digests and rubric/model/
corpus/provider versions. A changed result under the same operation UUID is stale.
Hashing source text does not anonymize records or replace consent/retention checks.
A selection snapshot remains the effective CV source even if mutable F2 changes.

Every mandatory requirement remains in scope, and each scoped requirement needs
an evidence or gap reason. The summary lists the complete scope. Alignment needs positive support
for every claimed requirement, cannot use an excluded screening result, cannot
ignore an ambiguous CV match or scoped interview concern. CV support must be an
original supported match. F5 positive support must be a supported completeness or
technical-accuracy dimension tied to a mapped question with non-uncertain topic
mapping; relevance/articulation or topic mention alone is insufficient. Mixed
needs an actual concern/partial/uncertain finding, never only absent evidence.
Insufficient needs an actual gap reference. All IDs are checked against the exact
fresh report. Ambiguous/unavailable F5 cannot support interview-dependent scope.
A genuinely missing application has no confirmation; historical reports lacking
current confirmed criteria cannot be newly confirmed.

GET never writes. Pending means no current row. Stale/restricted responses return
no position, scope, rationale references or reviewer attribution; only a version
and fresh token for deliberate reconciliation. Privacy restriction has precedence.
No automatic retry follows an uncertain PUT response: refresh, inspect version,
then deliberately reconcile. One current row is replaced; no immutable audit-history
claim is made. Physical purge removes the version too, so later reads may be pending.

## Retention compatibility and deletion

Engineering policy approved for synthetic development, NOT trainer/legal policy:
confirmation expiry is at most 30 days after confirmation and, for interview scope,
no later than its source deadline. The database enforces the 30-day maximum.
The current CV/application models contain no shorter deadline and no application-
wide deletion endpoint. No existing retention rule conflicted with this policy.
Do not claim a missing filesystem CV is a deleted application: original F6 allows
persisted selection evidence to survive mutable source changes. A future source
retention field must shorten this policy, not be ignored.

Mixed-source confirmation is bound to the interview parent. Withdrawal commits
its existing fence before physical cleanup. Readers deny the dependent judgment
immediately; cleanup deletes it before derived F5/source deletion. Cleanup failure
cannot restore visibility. Interview FK cascades cannot block analysis deletion;
operation UUIDs are metadata, not restrictive FKs. A separately confirmed CV-only
record has no interview dependency; an old mixed record is never silently converted.

Job/reviewer/optional interview deletion cascades confirmation. Deferred triggers
remove confirmation when an exact application's last persisted score/snapshot
source is deleted. Deferral preserves same-transaction F2 replacement; changed
replacement payload becomes stale instead. This does not invent a CV deletion API
or infer a deletion from an absent file. Bounded maintenance deletes expired,
privacy-restricted and orphan records independently of feature serving flags.
GET denial does not depend on maintenance success. Pre-0015 installations are
recognized by maintenance/cleanup and remain supported while serving is disabled.

## Activation and UI

`REVIEWER_CONFIRMATION_ENABLED=true` is opt-in and honored in development only;
apply migration `0015_reviewer_confirmation` to an approved database first. Default
is disabled, so an unmigrated home/legacy DB still serves existing F6. No local .env
is changed automatically. The existing home DB was not migrated for this increment.
Single report, comparison and isolated native print copy use one validated
confirmation projection. CV-only scope, reviewer/time/expiry, structured reasons
and technical reference IDs are explicit. Component memory only, acknowledgment
required, no free-text input, no background save. Browser retention and print
preparation also honor confirmation expiry. PDFs/paper cannot be remotely revoked.

## Evidence and remaining limits

See `../f6_consolidated_assessment.md` for exact commands/results. Migration
upgrade/downgrade/re-upgrade and tests use a newly created disposable local database
on the existing PostgreSQL image. No production/private home data is migrated.
No model or external API calls are needed. Full native print acceptance, F2 lost
unscored matches, application-wide deletion/retention policy, delegated reviewers,
full history and explicit ambiguous-analysis selection remain separate work.

## Deployment update — 18 October 2026, synthetic home only

Following separately approved backup/recovery verification, the normal
`talenttrace_home` database is now at `0015_reviewer_confirmation`. The original
source records and project-root `.env` were preserved. Session-local development
activation is enabled; inference, transcript storage, email and LiveKit demos
remain disabled. One CV-only confirmation survived an actual home backend restart.
The full private pre-migration backup was restored and verified in a separate
recovery DB before migration. See the final activation section of
`../f6_consolidated_assessment.md` for commands, counts and limitations.

This updates the earlier deployment state, not the evidence/privacy architecture.
It is neither permanent OS startup configuration nor non-synthetic acceptance.
Feature development is frozen for BJIT viva preparation; no new feature is implied.
