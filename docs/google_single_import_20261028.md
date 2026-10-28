# One approved Google Form application → current Docker intake

28 October 2026, branch feature/office-20261026-acceptance; starting HEAD 483c251.

## Live result: PASS for one authorized application only

Owner established nine historical responses on/before 15 October and one approved synthetic response on 28 October, with responses temporarily disabled. Exactly one Forms responses.list request used server-side `timestamp > 2026-10-16T00:00:00Z`, pageSize=1. It required one response, no nextPageToken, a creation timestamp after the cutoff, the approved synthetic identity, exact Job Reference, explicit configured consent and one PDF/DOCX attachment. No second page, old response or unrelated file was requested.

Fresh owner OAuth files in LOCALAPPDATA remained private and unmodified. The existing three read-only scopes/client identity were checked; access-token refresh, if needed, stayed in memory. Only the associated Drive file's metadata and bytes were read. Folder, download permission, type, size, Drive MD5, signature and SHA-256 were checked. No CV text or raw response was logged or added to Git.

Current authenticated recruiter/job resolution verified **TT-JOB-49C51587C3524024, revision 2**. Docker labels/application-volume identity and the worker's actual DB/user/schema/storage checks excluded historical databases. Source form/question/folder/consent fields were reused from local adapter configuration; its old recruiter/job/source/database/OAuth binding was NOT copied. The current job binding came from authenticated APIs. Intake does not confirm screening criteria or run models.

`ApplicationImportBridge` and `ExternalCvImportService` created exactly one pending_review ledger entry and its native private storage file. The worker holds the current owned-job lock through the existing importer's commit, using one shared session, preserving revision validation. Existing ownership, importer integrity, source uniqueness, deletion fence and contact provenance contracts remain. Google RESPONDER_INPUT contact is not verified mailbox ownership. Stable source identity derives from the form, and the submission key hashes form + response ID, matching the existing adapter's duplicate-prevention principle. No native-upload substitute was used.

Authenticated API and real Home after Refresh both showed **1 received / 1 new / 1 available / 1 trusted import**, zero viewed. All other owned-job counts, including existing Task 2 jobs, were unchanged through API comparison. No manual count writes, acknowledgement, LLM screening, publishing, deployment/restart or migration occurred.

## Implemented one-shot procedure

- `docker/google_import_once.py`: explicit owner-confirmation flag, private selection, fresh OAuth, current API identity/count checks, one durable request intent, bounded filtered read/file download and existing backend worker invocation. No scheduler, public endpoint, new database or automatic retries.
- `backend/app/services/google_single_application.py`: deterministic boundary/identity/consent/metadata/byte checks adapted from existing Google intake contracts; no I/O.
- `backend/app/google_application_import.py`: stdin-only worker executed through docker exec, using installed current bridge/services/settings. It does not install code into or replace the running image. Credentials never enter its payload. File bytes exist transiently in memory until existing trusted storage commits.

Private selection/intent/result/screenshot: ignored `data/google-one-import-20261028/`. **Do not rerun this completed operation.** Its request intent and expected-zero preflight prevent another scan/import. After an interrupted/uncertain outcome, inspect exact ledger/storage evidence under separate authorization; do not delete the intent or rotate source IDs to force another attempt. Native import services support identical retry reuse; live duplicate execution was intentionally not performed.

For review only, the completed invocation was:

```text
python docker/google_import_once.py --selection data/google-one-import-20261028/selection.json --confirm-one-synthetic-import
```

The CLI is intentionally fixed to this owner-approved job, runtime and cutoff. It is not automatic synchronization or a general ingestion service. OAuth credential files, private source IDs, consent selection, CVs and login files remain outside Git. No healthy runtime service was changed; the pre-existing manual compose.groq.yaml modification remains separate.

## Offline validation and limitations

**57 passed, 3 skipped, zero failures in the final focused run:** new single-response guards plus existing bridge, importer and notification tests. Covers ambiguous/paged/old responses, invalid consent, wrong job/synthetic identity, duplicate source keys, unsafe/changed files, idempotent native storage/ledger imports, ownership and notification deduplication. The three PostgreSQL opt-in tests were not enabled against preserved databases. The actual authorized Docker import/HTTP/Home checks above are separate live evidence.

An initial test mount made the inferred repository root `/`, causing 19 storage-guard failures. Correcting the test mount to `/verify/backend` resolved them without weakening application safeguards. New validator unit checks also passed on the host. No broad frontend suite/build was necessary because no frontend source changed. This is a successful bounded synthetic import, not broad Google connector, screening, unattended sync or real-candidate production acceptance.
