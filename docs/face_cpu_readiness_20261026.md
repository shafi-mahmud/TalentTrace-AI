# Actual YuNet/SFace CPU readiness — 26 October 2026

**Initial run: model provisioning/load PASS; face-model matching acceptance PARTIAL/BLOCKED.**

Follow-up: [bounded matching proof](face_matching_proof_20261026.md) now records
actual SFace comparisons for a modest transformed sample and a separate procedural
design. The latter remains highly similar; independent identity discrimination
and real biometric acceptance are still unverified. Initial evidence below is preserved.
This replaces numeric-simulation results as the evidence for actual model readiness.
It does not turn the existing synthetic-only HTTP demonstration into real enrollment.
The application remains disabled by default and accepts only built-in numeric
fixtures. No production biometrics, camera, external recognition, DB change or live
interview was used. No Docker, Ollama or Faster-Whisper process was started.

## Approved isolated assets

Private ignored root: `data/face-cpu-20261026/` (directory mode 0700).
Its separate `venv/` contains `opencv-python-headless==4.10.0.84` (cv2 4.10.0) and
`numpy==1.26.4`. Main application pins/environments are unchanged. Installed with
binary wheels only, no pip download cache. Total local footprint about **263 MiB**;
root filesystem still reports approximately **15 GiB free**.

Official repository snapshot: `opencv/opencv_zoo` commit
`48b10fa505aeb51fbd127fc60a5c660040e823b7`. Binary URLs use that fixed commit under
`https://media.githubusercontent.com/media/opencv/opencv_zoo/`.
The official raw Git LFS records supplied independently checked expected sizes and
SHA256 OIDs; downloaded files matched both exactly and were not LFS pointer text.
The CPU adapter also revalidated checksums before loading them.

| Model | Bytes | SHA-256 | Directory license |
| --- | ---: | --- | --- |
| face_detection_yunet_2023mar.onnx | 232589 | 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 | MIT |
| face_recognition_sface_2021dec.onnx | 38696353 | 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 | Apache-2.0 |

References: [official YuNet LFS record](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/face_detection_yunet_2023mar.onnx),
[SFace record](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface/face_recognition_sface_2021dec.onnx),
[YuNet license](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/LICENSE),
[SFace license](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface/LICENSE).
Licenses, license checksums and source URLs are preserved in private `licenses/`
and `manifest.json`. No weights, wheel binaries, images or private reports are in Git.
Licensing does not certify training-data rights, demographic fairness or deployment
fitness. No provider benchmark accuracy was substituted for measurements here.

## Actual execution, one bounded image batch

No authorized existing artificial face samples were found. The readiness script
created two entirely procedural, cartoon-like identities from original ellipses,
shading, seeded texture and geometric facial features. No photograph, learned image
generator, cloud service or unidentified person's image was used. Identity A's
probe was a small brightness/translation variant; B had different fixed geometry.
Fixture parameters were chosen before inference; quality thresholds were not relaxed
and rejected samples were not iteratively adjusted to force a match.

OpenCV DNN CPU target, one OpenCV/BLAS thread, OpenCL disabled. The invocation had
an external 90-second timeout; resource gates require 1200 MiB available initially
and stop before a subsequent sample below 700 MiB. No gate fired.

| Input | Actual YuNet face count | Full existing adapter outcome | Seconds, full adapter |
| --- | ---: | --- | ---: |
| Artificial A reference | 1 | **128-value SFace feature extracted**, finite and nonzero | 0.1272 |
| Artificial A transformed probe | 1 | Rejected: `face_quality` | 0.0342 |
| Artificial B probe | 1 | Rejected: `face_quality` | 0.0328 |
| Uniform nonface image | 0 | Rejected: `no_face` | 0.0299 |
| Two artificial faces side by side | 2 | Rejected: `multiple_faces` | 0.0741 |
| Darkened, heavily blurred artificial A | 0 | Rejected: `no_face` | 0.0301 |
| Corrupt bytes | Not decoded | Rejected: `corrupt_sample` | Not separately timed |

Both models loaded in **0.2476 seconds**. Standalone detector executions took
**0.0261–0.0714 seconds**. Full adapter times include its own second detection,
quality checks and, only for the accepted reference, alignment/SFace extraction.
These are single-run readiness observations, not sustained throughput/latency claims.
Peak process RSS: **203.50 MiB**; available memory after the run: **1913.9 MiB**.
Swap was already nearly full; no system/service configuration was changed.

**No valid pair survived all quality gates, so no real pairwise similarity score
or same/different identity accuracy is available.** A loaded recognizer and one
valid reference embedding do not establish matching. The previous numeric scores
are still simulations and are not reused as SFace results. The degraded input
failed detection; this does not independently validate a blur cutoff on a detected
face. Missing/multiple/corrupt/poor-input rejection was observed as shown.

Sanitized evidence: private `reports/readiness.json`, `reports/run.log`,
`fixture_manifest.json`; no raw images, face coordinates or feature vectors appear
in reports. All generated PNGs were removed after the run; `fixtures/` was checked
empty. RAM vectors were released, without claiming secure erasure from Python/swap.
The committed runner additionally cleans only its own created fixtures in `finally`
on errors, refuses existing fixture files and refuses overwriting acceptance evidence.

## Reproducible code and verification

`backend/scripts/face_cpu_readiness.py` is an explicit `--synthetic-only` offline
runner, not a downloader or enrollment endpoint. It only generates its own fixed
geometry. It requires a private root inside project `data/`, separately provisioned
pinned model files and empty output paths. Existing evidence is frozen: do not
rerun over this root. A future controlled run should reuse verified models in a
fresh private run directory, not redownload them or overwrite these results.

Example invocation from the repository root for a newly prepared private root:

```sh
PYTHONPATH=backend timeout 90s data/face-cpu-20261026/venv/bin/python -B \
  backend/scripts/face_cpu_readiness.py --root data/<fresh-private-run> --synthetic-only
```

The real adapter and numeric regression demo share pure 128-dimensional finite
cosine arithmetic in `integrations/face/metrics.py`. Neither metric arithmetic nor
an illustrative threshold certifies identity or decides hiring.

**63 focused tests passed, zero failed/skipped**: consent, exact interview/session
isolation, recruiter authorization, withdrawal, expiry/cleanup, optional adapter
contracts, fixed artifact metadata and normal/interrupted fixture cleanup. Tests
use synthetic SQL doubles and mocked OpenCV except the separately recorded actual
CPU run above. No application database was modified. Diff checks passed.

## Remaining physical-viva blockers

- Obtain suitable, explicitly approved artificial samples and measure actual
  same-identity and different-identity pairs without weakening quality gates.
- Calibrate recognition/quality thresholds and evaluate lighting, pose, device,
  demographic and accessibility variation; cartoons are not human acceptance data.
- Approve biometric consent/purpose/retention policy, protected reference/key storage,
  deletion/backup lifecycle and independently authorized on-site comparison after
  online invitations expire. These remain absent; no persistence was added.
- Design delayed-result/withdrawal fences before wiring inference to the web flow.
  Static photo matching does not prove liveness or who originally enrolled.
