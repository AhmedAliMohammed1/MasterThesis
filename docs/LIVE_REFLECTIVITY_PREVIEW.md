# Live clipped-reflectivity preview — 21 November 2026

The user requested the new encoding and score gate0.3 to judge visually. The current
run uses raw01 at1.0 speed with `min(reflectivity/100,1)`, not unrestricted division
by100. Geometry and point selection are unchanged. RViz remains on domain99 and
frame ouster1_lidar. This is a local diagnostic preview, not NVIDIA-endorsed Ouster
calibration or accepted detection accuracy.

The adapter now exposes read-only `intensity_clip_max`, default0 (disabled), in
C++, ROS launch, the combined supervisor and the shell launcher. Invalid caps fail
validation. A positive cap is applied after successful numeric division. Existing
baseline defaults remain reflectivity/255, clipping disabled and launcher gate0.4.

```bash
PP_IMAGE=pp-infer:reflectivity-preview-overlay \
  PP_OUSTER_INTENSITY_DIVISOR=100 PP_OUSTER_INTENSITY_CLIP_MAX=1 \
  PP_CONFIDENCE_THRESHOLD=0.3 bash tools/start_ouster.sh bag
# Separate terminal:
PP_BAG_RATE=1 bash tools/start_ouster_bag.sh raw01
```

The8 native CPU/ROS CTest checks and16 Python launcher tests pass. Clipping tests
cover uncapped compatibility, preserved geometry/header, cap behavior, invalid caps,
ROS transport and read-only parameters. Native adapter smoke testing in the saved
runtime succeeded. To preserve the detector environment, a derived runtime image
copies only the new adapter executable over the baseline image. The attempted full
Docker dependency build was intentionally canceled and its log retained. Normal
full Docker builds include the new source and tests; no complete full-image build
is claimed in this preview.

Three timestamp-matched raw/adapted clouds exactly match the desired float32
encoding; XYZ including NaNs and headers are preserved. Each retains131072 raw
points. Measured intensities span0–1;918–925 source points in those clouds exceed
100 and are capped. The short live sample received24 detection arrays, with1–7
published boxes per array. Sampled diagnostics reported96 received/converted,
zero rejected,96 processed,zero invalid clouds and zero inference errors. Counts
are asynchronous snapshots, not unique objects or an accuracy evaluation.

NVIDIA findings: the exact publisher manifest/hash matches local v1.1 ONNX, but
its version description is empty and only model/labels are provided. The shared
card's ETLT BEV/3D mAP66.6860%/52.8530% is not average confidence and cannot be
certified as exact-v1.1 ONNX/Ouster performance. No mean-confidence target was
found in the reviewed NGC API/card, TAO docs, NVIDIA blog or official ROS README.
Use the same LiDAR/configuration as training, verified coordinates and training-
compatible reflectance; generic examples are not a replacement for this export's
actual tensor/voxel/decoder contract. /100 clipping remains our experiment.

- [Exact model and confidence research](NVIDIA_EXACT_MODEL_CONFIDENCE_RESEARCH.md)
- [NVIDIA settings research](NVIDIA_POINTPILLARS_SETTINGS_RESEARCH.md)
- [Validation record](../config/reflectivity_preview_validation.json)

Original API responses, source hashes, binary, build recipe, logs, desktop capture
and exact live checks are preserved under
`.recovery/verification/reflectivity-preview-20261121/`.


## Later verification and screenshot investigation — 21 November

The original preview above started raw01. The later user-requested replay switched to ouster1 at rate 1.0 with the same clipped /100 and gate 0.3 settings. These are dated configurations, not a guarantee about current processes.

The [latest report](OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md) records 2,268 additional controlled GPU inferences and six exact-person inferences. Clipped /100 did not establish a pedestrian accuracy improvement. Screenshots, generated plots and drafts are retained in [the image archive](IMAGE_ARCHIVE.md). No output-height correction or offline sampling policy was promoted live.
