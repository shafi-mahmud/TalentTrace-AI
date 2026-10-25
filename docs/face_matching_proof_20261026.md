# Bounded actual SFace comparison — 26 October 2026

**Actual CPU comparison executed. Transformed-image consistency established;
independent identity discrimination and physical-viva verification remain unverified.**

Branch: `feature/face-verification-viva`, starting at `f0a859b`.
One bounded attempt, no retries/threshold search, downloads, Cloud activity,
webcam, real candidate data or persistent biometric database. The existing
synthetic-only application feature remains disabled by default. Its numeric API
results are not used as face-model evidence.

## Why the previous probes were rejected

The exact previous A reference, transformed A probe and B probe were regenerated.
Their PNG SHA256 values matched the original private fixture manifest, confirming
these were the same procedural samples, using the same isolated runtime/models.

| Sample | Actual YuNet confidence | Existing minimum | Result |
| --- | ---: | ---: | --- |
| A reference | 0.9067394 | 0.9 | Accepted |
| Original transformed A probe | 0.8696949 | 0.9 | Rejected: face_quality |
| Original B probe | 0.6879843 | 0.9 | Rejected: face_quality |

Both rejected probes had one detected face and satisfied the measured size,
area, bounding-box and landmark-in-box checks. The confidence floor explains
rejection; there is no evidence of an adapter defect. Their failure does not
justify lowering confidence, bypassing other gates or fabricating embeddings.

## Preselected follow-up samples

- Reused the accepted artificial A reference, generated from its original geometry.
- Created exactly one mild A probe: add one brightness level to each 8-bit channel
  (saturating at 255), with **no translation, warp or resampling**. Confirmed its
  decoded pixels differ from the reference. This is a highly correlated transformed
  image, not an independent photograph or independently authenticated person.
- Generated one additional design C from separate fixed procedural parameters:
  face axes 140/174, different skin shading/texture seed, eye spacing/height, nose
  and mouth positions. It was rendered independently, not obtained by transforming
  the A image. The generator's A/B outputs remain unchanged, confirmed by hashes.
  Different procedural designs are not evidence of different real human identities.

All three were accepted by the **unchanged** existing confidence, size, clipping,
landmark/pose, lighting, contrast and blur checks. Each passed actual YuNet detection,
SFace alignment and finite nonzero **128-dimensional** embedding extraction.

| Actual comparison | Cosine similarity | Established interpretation |
| --- | ---: | --- |
| A reference → mild A probe | **0.99940291** | Strong consistency for this tiny brightness transformation |
| A reference → independently generated C | **0.90649607** | Different artificial designs remain highly similar in this embedding space |

The C score is **not** a successful nonmatch/discrimination result. Both values
exceed the earlier illustrative OpenCV 0.363 threshold; applying that example
threshold would not separate these cartoon designs. It was neither recalibrated
nor used to certify identity or make a hiring decision. No population-level
accuracy, false-match rate, fairness or liveness conclusion follows from this run.

## Runtime, safety and evidence

Reused ignored OpenCV 4.10.0 / NumPy 1.26.4 environment and previously verified
YuNet 2023mar/SFace 2021dec binaries. New private ignored root:
`data/face-match-20261026/`. Model files are hard links to existing verified inodes,
not repeated downloads or modified weights. Fixed expected hashes are checked
by the adapter before loading. The prior run/evidence remains untouched.

CPU/OpenCV DNN, one OpenCV/BLAS thread, OpenCL disabled; external 75-second deadline.
Available memory gates were retained (1200 MiB initially, 700 MiB before each sample).
No resource gate fired. Observed model load **0.3761 s**; full accepted image pipelines
**0.2723 s** (reference), **0.1073 s** (mild A), **0.1078 s** (C). Peak process RSS
**170.8 MiB**; available memory afterward **2059.9 MiB**. These are single-run
observations, not sustained performance acceptance.

Private sanitized reports: `reports/matching.json`, `reports/run.log` and
`fixture_manifest.json`. They contain hashes/counts/status/scores/timings, no image
pixels, face-coordinate arrays or feature vectors. Every generated face PNG was
removed by the owned-fixture `finally` cleanup; the fixture directory was checked
empty. Model files remain ignored. No runtime activation settings or DB records
were changed. Logical RAM release does not guarantee secure Python/swap erasure.

The committed `backend/scripts/face_matching_attempt.py` reproduces this exact fixed
attempt in a fresh private run root using verified existing models and the original
fixture manifest. Do not rerun over preserved evidence or search transformations
until a desired score appears. No further actual model execution was made after
this attempt. The only changes are the offline runner, fixed C generator parameters
and documentation; no face acceptance thresholds or authorization code changed.

Existing focused quality/consent/isolation/withdrawal/cleanup regressions were run.
No new application regression was manufactured: the diagnosed rejection is intended
behavior, not a defect. Physical-viva use still needs approved biometric policy,
protected enrollment storage/deletion/retention, independently authorized on-site
access after invitations expire, calibration, suitable independent samples and
separate spoof/liveness evaluation.

Verification result: **63 focused tests passed, 0 failed/skipped** (30.26 seconds),
covering existing quality/model-adapter contracts and consent, recruiter/candidate
isolation, withdrawal, expiry and normal/interrupted artifact cleanup. Diff checks
passed. SQL doubles/mocked OpenCV in these regressions are distinct from the actual
CPU comparison run reported above.
