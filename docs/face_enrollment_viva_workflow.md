# Synthetic online enrollment → viva review — 26 October 2026

**Implemented synthetic-only prototype; disabled by default. Not real candidate
biometric enrollment, liveness, identity certification or hiring acceptance.**
Builds on `fba18db`; existing trainer integrations and face-quality gates are preserved.
No migrations, application database changes, service restart, Cloud call, model
installation/download or real camera/image input was performed.

## Actual workflow

1. Operator separately configures an exact fictional interview → artificial design
   (`a` or `c`) mapping. Browser requests cannot supply photos, image paths, URLs,
   arbitrary embeddings, model files or a candidate identity.
2. In the existing connected interview, the candidate sees the synthetic consent
   wording and explicit configured retention duration. The checkbox starts unchecked.
   Candidate authentication uses the existing one-use invitation's scoped hashed
   cookie, current criteria/job ownership and online join window. Caption/storage/
   assistant/activity consents authorize none of this processing.
3. Candidate explicitly consents, then selects **Enroll synthetic sample**. A separate
   existing OpenCV interpreter generates the server-selected artificial PNG, validates
   pinned YuNet/SFace weights, detects exactly one acceptable face, aligns it and
   extracts the actual 128-value feature. Quality thresholds are unchanged.
4. The encrypted reference survives fresh vault instances and Python process restart,
   bounded by its original expiry. Repeated enrollment cannot silently replace it.
5. Under Saved interviews, only the owning authenticated recruiter can see enrollment
   status. A separate server viva allowlist is required to compare, including after
   the online join window and invitation's natural expiry. This does **not** extend
   candidate-cookie validity or create an anonymous on-site identity assertion.
6. Recruiter acknowledges human review and explicitly selects a same-design transformed
   probe or another server-generated design. The adapter processes a new PNG and
   compares it with **only this exact enrolled reference**; there is no face search.
   Results are provisional similarities, never match-certified/hire/reject outcomes.
7. Candidate may withdraw using the still-valid interview session after browser reload,
   or a purpose-limited withdrawal receipt even after the original session expires.
   The receipt authorizes deletion only, never status/results/enrollment. The UI keeps
   it only in component memory, offers explicit private copying and never renders it
   as page text, logs it or writes it to browser storage. If lost after session expiry,
   request recruiter deletion; no public receipt-restoration form is implemented.
8. Recruiter can delete the reference. Expiry deletes it automatically through the
   30-second maintenance loop and on access. Withdrawal removes feature/provenance
   immediately, retaining only an encrypted short-lived tombstone/audit until original
   expiry, preventing delayed inference from resurrecting the record.

No physical-human sample submission is enabled. “Same/other design” means only our
procedural fixtures, not a real person attending a viva.

## Persistence, authorization and lifecycle

New `FaceVault` uses a private Linux directory (0700), 0600 files, AES-256-GCM with
random 96-bit nonces, and interview/version-bound authenticated additional data.
Entire JSON contents are encrypted: exact recruiter/job/batch/upload/interview/
invitation/session-digest/criteria-revision scope, consent version/time, fixed expiry,
feature, model/sample provenance and bounded audit events. No raw images are stored
as references. Record filenames contain interview UUIDs; the private directory is
still sensitive. Cryptography **50.0.2** was already installed and is now an explicit
backend dependency; no main environment installation was needed.

Key comes only from private server configuration, is not written into the vault,
and must be retained separately across restart. Wrong/missing keys or tampered
ciphertext fail closed; they never cause automatic replacement. There is no key
rotation/recovery service, KMS integration or production backup governance.

Linux `flock` serializes short vault operations across processes; atomic replace,
file/directory fsync and run-ID checks protect writes. No inference runs under a
vault lock. A separate nonblocking worker lock admits one actual model process
per shared vault; busy workers fail rather than queueing memory-heavy inference.
This is a bounded local prototype, not distributed storage. Windows lacks this
vault implementation; disabled normal application startup remains supported there.

Every returned result revalidates recruiter/job/interview authority, current criteria,
invitation revocation/rotation and exact stored scope. Natural invitation expiry is
allowed only for separately authorized recruiter viva review. Revoked/rotated access,
criteria or synthetic-identity changes restrict reads. Source-record deletion denies
access; coordinated immediate source-deletion/N19 cascade is not implemented, so
use reference deletion/withdrawal or the fixed retention cleanup. No existing DB
candidate-deletion behavior was changed.

During asynchronous inference, withdrawal may proceed through the deletion-only
receipt without waiting for job-row locks. The final vault operation checks current
state and run ID, so a late completion cannot recreate a withdrawn/deleted record.
The UI invalidates pending responses and clears provisional output on withdrawal,
delete, errors or context change. Recruiter status polling clears withdrawn/expired
results, normally within two seconds; data already returned cannot be retracted
from a recipient or clipboard. No result is stored in the reference or browser storage.
Encrypted audit events contain names/timestamps only, no quotes, probes or scores.

Configured expiry is fixed at consent and **never extended by viewing/comparison**.
The lifespan worker continues cleanup while feature use is disabled if root/key/
retention configuration is retained. It also removes authenticated expired temp
ciphertexts and abandoned synthetic worker directories after a crash. Integrity/key
failures require operator review, not destructive automatic repair. Without the key,
application availability or filesystem access, deletion deadlines cannot be guaranteed.
Logical unlink/rewrite cannot promise secure erasure from snapshots, backups, swap
or SSD media. These are explicit barriers to real-candidate activation.

## Configuration: supported, not activated

All default values remain off/unset. There is no `.env` edit or auto-provisioning.

| Existing/new setting | Purpose |
| --- | --- |
| `FACE_WORKFLOW_ENABLED` | Defaults false; only enables server-generated artificial samples |
| `FACE_WORKFLOW_SYNTHETIC_IDENTITIES` | Exact interview UUID → `a`/`c` server-controlled mapping |
| `FACE_WORKFLOW_VIVA_INTERVIEW_IDS` | Separate explicit recruiter-viva comparison allowlist |
| `FACE_WORKFLOW_ROOT` | Existing private ignored directory under project `data/` |
| `FACE_WORKFLOW_KEY` | Private URL-safe base64 encoding of a 32-byte AES key, separate from vault |
| `FACE_WORKFLOW_RETENTION_SECONDS` | Required explicit expiry, 60–604800 seconds; no default |
| `FACE_WORKFLOW_PYTHON` | Existing approved isolated OpenCV interpreter |
| `FACE_WORKFLOW_MODELS` | Existing verified local model directory |

The approved interpreter/models are still in `data/face-cpu-20261026/`. No path or
credential can be supplied by browser input. Main interpreter does not import OpenCV.
Worker environment excludes unrelated provider credentials, runs CPU/one thread,
requires 1200 MiB available memory and has a 20-second client deadline. Timeout,
cancellation, bad samples or model errors fail closed; parent/worker cleanup removes
only its own synthetic PNG tree. No automatic retries, downloads or cloud fallback.

Before any later manual runtime demonstration, separately prepare private configuration,
map a fresh fictional interview and select an explicit expiry/key. Do not point this
prototype at real records. This implementation run created no booked interview,
invitation, consent or reference in the existing home database.

## API surface

- Candidate GET `/api/v1/interview-access/face-workflow`: wording, duration, own state.
- Candidate POST `/consent`, `/enroll`, `/withdraw` under that prefix: separate consent,
  exact run, authenticated withdrawal. Request schemas reject extra image/evidence fields.
- POST `/api/v1/face-workflow/withdraw`: interview UUID + secret deletion-only receipt;
  CSRF protection remains required. No read access granted by the receipt.
- Owned recruiter GET `/api/v1/jobs/{job}/interviews/{interview}/face-workflow`.
- Owned recruiter POST `/verify`: exact run, server-generated probe selection and
  explicit human-review confirmation; separate viva allowlist required.
- Owned recruiter POST `/delete`: works even if feature use was disabled, criteria
  changed or candidate access was revoked, while ownership/interview still exist.

All API responses use the existing no-store policy; no unauthenticated export/read,
real-image upload or arbitrary identity/embedding endpoint was added.

## Verification and remaining acceptance

Tests separate synthetic SQL-double authorization from actual model execution.
The actual-model gate is `TT_FACE_ACTUAL_MODEL_TEST=1`; it is not a runtime activation
setting. Tests reuse only approved local weights/interpreter in temporary ignored
private directories, delete references/PNG artifacts, and never change home settings.

- Encrypted reference recovery verified by a fresh vault and an **independent Python
  reader process**. The normal development backend was not restarted or activated.
- Actual local-model integration performs A enrollment, restart-safe reads, A-probe
  comparison and separate C comparison; it never asserts C is a successful nonmatch.
- Actual ASGI/auth/route → subprocess YuNet/SFace → encrypted persistence → new vault
  → recruiter comparison → withdrawal → deletion path was exercised. SQL execution is
  doubled; this is not live PostgreSQL/browser/physical-candidate acceptance.
- Security cases cover missing consent, wrong owner/session/candidate binding,
  independent viva permission, natural expiry vs revocation, key mismatch, tampering,
  retention, deletion, in-flight withdrawal, worker failure/cancellation and cleanup.
- React tests cover disabled/unchecked controls, explicit consent, human review,
  sanitized errors, withdrawal clearing and restored-session withdrawal. Desktop/
  mobile visual appearance and real browser end-to-end behavior are unverified.

Real-candidate activation remains blocked by approved biometric purpose/consent
wording and non-biometric handling policy, production encryption/key management and
backup deletion, coordinated source-erasure controls, representative sample/quality/
fairness evaluation, spoof/liveness design and a separately approved on-site staff
identity/authorization process. The high prior C similarity (~0.9065) demonstrates
why these drawings are not proof of identity discrimination. Static images do not
prove liveness or who enrolled. No automatic rejection or identity certification.

### Final executed evidence

- Earlier combined focused backend run: **82 passed, zero failed/skipped**.
- Latest workflow suite: **23 passed, zero failed/skipped** with the explicit actual
  model gate enabled, including new-process encrypted reads, actual-model storage
  restart, authenticated HTTP enrollment/comparison, restored-session withdrawal,
  in-flight revocation, cancellation and crash-artifact cleanup. These runs overlap;
  counts are not additive. A separate real-model HTTP check also passed before the
  latest combined workflow run.
- Full latest frontend suite: **337 passed**, zero failed/skipped. TypeScript and
  production build passed; existing large interview-bundle warning remains.
- Default runs skip the two actual-model tests unless explicitly enabled. Tests that
  use vectors/fake recognizers are not relabelled as actual model evidence.
- Actual test vaults and PNG directories were removed; approved models remain ignored.
  No home backend restart, migration, persisted home reference or browser/physical
  enrollment was performed. No face data, key or withdrawal receipt is committed.
