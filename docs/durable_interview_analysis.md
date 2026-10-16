# Durable synthetic interview analysis

Implemented, opt-in: `INTERVIEW_EVALUATION_DURABLE_ENABLED=true` uses PostgreSQL
instead of the default temporary single-worker analysis store. It still requires
the development/synthetic-job allowlist, configured Groq model, separate external
processing disclosure and authorized finalized source transcript.

Migration `0014_interview_analysis` follows `0013_transcript_lifecycle`. It adds
only `interview_analyses`; upgrade/downgrade/re-upgrade is exercised on a disposable
database. No existing demo database is migrated by this sprint.

## Identity and recovery

An operation UUID scopes a recruiter, job, interview, current criteria revision,
source digest, rubric, configured model and reference corpus version. A unique
input/model/rubric/corpus key deduplicates independent workers. Repeating a request
returns existing running/completed/failed state; it does not silently call Groq.
Only completed operations expose a result; failures contain fixed safe codes.

A committed running claim has a 150-second lease and random claim ID. The
110-second workflow deadline is shorter than the lease. No database transaction
is kept open during inference. Status checks mark expired leases failed with
`evaluation_worker_interrupted`; they never restart work. A deliberate retry needs
the current failed attempt number, increases the attempt and replaces its claim.
A late old worker cannot commit over the new claim. An uncertain network/provider
outcome can still have consumed provider quota; retry is never cost-idempotent.

The UI has a separate unchecked retry disclosure. Request delivery uncertainty
requires checking the retained operation first. A full page reload loses the
component's operation UUID, but repeating the same finalized input is deduplicated
by the backend. No transcript is saved in browser localStorage.

## Privacy transaction order

Each start, result commit and result GET revalidates the recruiter session,
ownership, revision, complete source, revocation and retention. The interview row
is locked before the analysis row, matching transcript withdrawal/cleanup.
Therefore a result commit serializes with withdrawal: work committed first is
subsequently inaccessible; withdrawal committed first prevents the later result
commit. Provider responses are not exposed as completed until this check commits.

The existing durable withdrawal fence commits before physical deletion. Cleanup
deletes and verifies derived analysis rows as well as source captures/turns, even
if the analysis feature is disabled. An unavailable table on a legacy 0013
installation is supported. Failed cleanup never clears revocation. Expiry denies
reads immediately; the existing retryable privacy sweep physically removes text.
The maximum source retention remains 30 days. Expiry/deletion does not claim
erasure of previously delivered provider input, browser screenshots or backups.

## Scope and limits

Implemented: durable identity/result, optimistic fenced retries, PostgreSQL
serialization and shared source privacy lifecycle. LangGraph executes Pair → Map
→ Retrieve → Assess → Validate; it is not using an additional checkpoint store or
resuming half a provider call. Worker failures rerun only on explicit approval.
No queue, Redis, automatic hiring decision or public transcript-writing API exists.
Production activation/disclosure review, operational capacity limits, encrypted
backup retention and longer real-world interview reliability remain separate work.

Verified with synthetic disposable PostgreSQL records: independent manager
deduplication; a fresh Python interpreter retrieving the saved authorized result;
explicit provider-failure retry; expired lease and stale worker fencing;
withdrawal during inference; failed deletion followed by denied reads and verified
cleanup retry; foreign ownership rejection; unrelated interview isolation; and
retention expiry followed by derived-row deletion. Automated inference is mocked.
