# Face-verification viva prototype — 26 October 2026

**PARTIAL. No real biometric enrollment or physical-viva identity verification is enabled.**

Follow-up: [actual CPU readiness](face_cpu_readiness_20261026.md) now records approved
model provisioning, real YuNet detections and one real SFace embedding. The initial probes
failed unchanged quality checks. A [later bounded comparison](face_matching_proof_20261026.md)
established transformed-image consistency, but not independent identity discrimination. The original
numeric API below remains explicitly simulated and disabled by default.
Branch: `feature/face-verification-viva`, based on `579eeca` (includes `5127f7f`).
No F3/F4/F11 changes, migrations, new dependencies, capture, model downloads or
external recognition calls. No actual face images or biometric embeddings were used.

## What runs now

An isolated FastAPI demonstration accepts only four built-in artificial **numeric
vector** fixture identifiers. No image, base64, path, upload, camera or embedding
field is accepted. These vectors are NOT face-model outputs. The offline script
and authenticated API exercise actual 1:1 cosine arithmetic and the enrollment,
consent, authorization, expiry and cleanup implementation; they do not demonstrate
face-recognition accuracy. Results explicitly say `mode: simulated_vectors`,
`model_used: null`, `identity_verified: false`, `liveness_checked: false`.

- Disabled by default: `FACE_SYNTHETIC_DEMO_ENABLED=false` and an empty
  `FACE_SYNTHETIC_DEMO_INTERVIEW_IDS` server-side UUID allowlist. Even enabling both
  permits only numeric fixtures, never real biometrics. No home setting was changed.
- The candidate uses the existing scoped, hashed interview session cookie, current
  invitation, ownership/criteria validation and join window. Caption, storage,
  activity and F11 consents do not authorize this separate demonstration.
- Candidate reviews `/api/v1/interview-access/face-demo/consent` and explicitly
  accepts `face-synthetic-demo-v1`. Its wording explains temporary use, withdrawal,
  no identity certification and a manual non-biometric alternative. Declining means
  not opting in; nothing in booking/join or hiring depends on this feature.
- Only an authenticated owning recruiter can enroll, compare or retrieve a result.
  Each action rechecks job ownership, current interview, invitation/session validity
  and the enabled allowlist. Recruiter enrollment/comparison require explicit review.
- Binding is the exact recruiter/job/batch/upload/interview/invitation/session-digest/
  criteria-revision tuple, constructed by the server. Browser input cannot choose a
  candidate, supply an embedding or search a database. A changed binding invalidates
  the old reference rather than comparing across sessions or candidates.
- At most 16 RAM-only references, each with a fixed five-minute timer. Comparisons
  do not extend retention. Candidate withdrawal or recruiter deletion clears result
  and reference; mutable reference/probe arrays are zeroed before release. This is
  logical cleanup, **not guaranteed secure erasure of Python/process/swap memory**.
  Restart loses all state; there is no cross-worker synchronization or durable audit.
- Revoked/expired access restricts recruiter reads and removes the reference when
  detected. Missing interview/criteria/allowlist authority never returns a result;
  an otherwise unreachable entry still expires within its original five minutes.
  Disabled-feature requests clear the store. No database writes or files are needed.

Existing parent job-row locks serialize invitation decisions with these short
synchronous operations within the normal request transaction. No real image inference
runs while holding those locks. Production asynchronous inference would require its
own cancellation/generation fences and concurrency tests, not this demo's assumptions.

## Repeatable offline proof

From `backend`, using an existing approved Python runtime with project dependencies:

```sh
PYTHONPATH=. python -B scripts/face_synthetic_demo.py --synthetic-only
```

The explicit flag is mandatory. The script constructs wholly fictional scope IDs,
consents, enrolls A, compares A's probe and B's probe, then clears its store in
`finally`. It does not authenticate a person, contact HTTP, use the application DB,
load a face model or write private artifacts. Expect approximately 0.99995 (above
illustrative threshold) and 0.01 (below). Neither outcome is a pass/fail or hiring gate.

API demonstration, only in a separately approved synthetic interview runtime:

1. Enable the synthetic flag and exact fictional interview UUID in session-local
   configuration. Use two independent authorized recruiter/candidate sessions.
2. Candidate GETs consent wording, then POSTs
   `{"version":"face-synthetic-demo-v1","decision":"accept"}` to the same path.
3. Recruiter POSTs `{"run_id":"<returned UUID>","review_confirmed":true,
   "fixture":"vector-a-reference"}` to
   `/api/v1/jobs/<job>/interviews/<interview>/face-demo/enroll`.
4. Recruiter POSTs the same scope/review fields with `vector-a-probe`, then
   `vector-b-probe`, to `/face-demo/compare`. Results are returned independently.
5. Candidate POSTs `{"run_id":"<UUID>"}` to
   `/api/v1/interview-access/face-demo/withdraw`, or recruiter POSTs it to
   `/face-demo/delete`. Further reads/comparisons fail. Disable the session profile.

No such runtime, interview, invitation or consent was created during this increment.
Existing media/camera controls are not reused for capture and were not modified.

## Optional actual CPU adapter: prepared, not accepted

`app/integrations/face/opencv_cpu.py` implements a lazy, optional OpenCV adapter:

- Specific unquantized `face_detection_yunet_2023mar.onnx` and
  `face_recognition_sface_2021dec.onnx`, OpenCV Python API >=4.8 and <5. CPU/OpenCV DNN
  targets are explicit. OpenCV 5's newer dynamic YuNet default is intentionally not
  assumed compatible. Quantized/new variants are rejected by filename.
- Separately approved local artifacts require operator-supplied SHA256 pins;
  checks happen before model construction or image decoding. There is no downloader.
  Trust requires an immutable, restricted, independently reviewed artifact directory;
  computing a hash of an arbitrary supplied file does not prove it is synthetic.
- PNG-only artificial fixtures are size/dimension bounded before decoding. Detector
  must return exactly one face; absent/multiple/nonfinite/clipped/small/low-confidence
  detections, implausible landmark pose, low light/contrast and blur are rejected.
  Five-landmark alignment precedes a finite, nonzero, 128-value SFace feature.
- These conservative heuristic thresholds are uncalibrated. A missed second face,
  detector error, occlusion or spoof is still possible. They cannot guarantee quality.
- Adapter is deliberately **not wired to HTTP enrollment**, camera or persistence.
  Its OpenCV contract and quality gates are tested with mocks and synthetic arrays.
  Binary/NumPy ABI compatibility, actual models, CPU latency, memory, detection,
  alignment and recognition on approved artificial faces remain **UNVERIFIED**.

At original commit `8c7ec8b`, inventory found no cv2 in system or the approved STT interpreter, no YuNet/SFace
weights in checked project data, and no approved artificial face-image fixtures.
Nothing was installed/downloaded. **Original increment actual model used: none.** Both positive/negative
outcomes above are vector simulations, not successful face-model comparisons.

## Licensing / compatibility evidence

The official [YuNet directory license](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE)
is MIT. The [SFace directory license](https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/LICENSE)
is Apache-2.0; preserve applicable licenses/notices if approved artifacts are later
redistributed. The [official SFace example](https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/demo.py)
uses the 2023mar detector and 2021dec recognizer. The
[OpenCV 4.x tutorial](https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html)
describes detection, alignment and cosine matching, including an example 0.363
threshold. That example is not measured/calibrated acceptance for our participants.
Directory licensing does not establish participant consent, training-data rights
clearance, fairness, deployment accuracy or permission to collect biometrics.
Only official documentation was fetched; model/image files were not downloaded.

## Gates before real enrollment or on-site use

1. Approve model/runtime provisioning and explicitly artificial fixture provenance;
   pin versions/checksums/licenses, isolate dependencies and run actual CPU tests.
2. Approve an informed biometric policy: controller/purpose, specific optional consent,
   accessible manual alternative, withdrawal/deletion process, lawful retention period,
   participant rights and no adverse decision solely from similarity. This document
   is a technical design, not an approved policy or legal assessment.
3. Design protected reference storage: encryption/key custody, least privilege,
   scoped audit without face data, immutable enrollment provenance, deletion cascades,
   backup expiry and retention worker. Existing interview/candidate tables have no
   approved face-reference or biometric-consent record; none was added here.
4. Define separately authorized physical-viva access after online invitations expire.
   Current invitation possession is not identity proof; the five-minute demo cannot
   bridge days or certify who enrolled. Never extend join windows to bypass this gap.
5. Validate spoof resistance/liveness separately. Static photo comparison accepts
   photographs/screens; it is not liveness detection. Evaluate lighting, pose, age,
   skin tone, camera quality, false matches/nonmatches and accessibility across the
   intended population; approve a human review policy and calibrated uncertainty band.
6. Validate delayed inference/withdrawal races, multi-worker authorization, resource
   isolation and cleanup before connecting any real adapter to an enrollment API.

No demo result certifies identity, establishes cheating, or triggers hire/reject.


## Executed verification

- **88 backend tests passed, 0 failed/skipped** (28.19 seconds): new synthetic
  lifecycle/API/quality-adapter tests plus existing invitation, attention, Telegram
  and CV-provider regressions. Authorization uses real routes/authentication with
  synthetic transactional SQL doubles, not a real PostgreSQL or Cloud service.
- Offline CLI ran once: A/A similarity **0.999950**, A/B **0.009999**. Both results
  explicitly identify simulated vectors/no model/no identity or liveness proof.
  Store was cleared in `finally`; temporary synthetic artifact directories were
  removed by context managers and checked absent. No ignored private files created.
- Model tests use mocked OpenCV and synthetic arrays; no actual face model ran.
  Frontend/media source is unchanged, so no browser/physical acceptance is claimed.
- Diff checks passed. Initial tests launched from the repository root hit an
  existing relative Alembic-config test; the correct backend-directory rerun passed.
  It generated offline migration SQL only; no application database was modified.
