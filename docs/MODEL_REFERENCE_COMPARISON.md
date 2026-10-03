# What the independent model comparison found

Measured on 3 October 2026. The poor KITTI baseline is reproduced in an independent TensorRT 8.6 environment. The evidence does **not** support blaming the pretrained weights alone. We now have a shared preprocessing/capacity concern to investigate, as well as the model's input/training conventions. Accuracy acceptance and exact numerical parity remain unmet.

The existing production image, ONNX, engine, ROS source and first KITTI measurements were preserved. This investigation adds diagnostic tools and separate Docker images. Nothing was retrained, no z correction was installed, and no detection thresholds were tuned.

## The comparison in plain language

We gave exactly the same point clouds to the same ONNX model in two environments. One used the existing TensorRT 10.16.1.11 engine and libraries. The other built a new FP32 engine with TensorRT 8.6.1.6, CUDA 12.0 and its own NVIDIA plugin library. Both ran on the same physical GPU. Every input's original bytes, padded bytes and point count were hashed. Each of the 32 frozen frames was run three times in each environment: 192 raw inferences in total.

The small diagnostic runner uses TensorRT's APIs directly and contains no ROS or pp_infer inference code. Its older path uses enqueueV2; its current path uses enqueueV3. It checks output counts and saves the actual FLOAT32 values in binary form, avoiding rounded trtexec JSON. It is a diagnostic adapter, not an untouched execution of the complete original NVIDIA sample.

For filtering, we compiled NVIDIA's original sample NMS source unchanged at recipe revision `a540badc47812a17a94e924b537d49ad3969b5a8`. We also compiled our existing CPU NMS unchanged. Applying both to the same raw candidates isolates filtering from inference. **All 192 observations selected the same boxes**, using unique matching with a 0.000001 component tolerance. Box order is not an accuracy criterion.

The separate TensorRT 8 environment is a compatibility reference for this exact export. NVIDIA's sample documents older TensorRT/ETLT deployment; it does not provide a trusted original-training output fixture for this particular deployable_v1.1 ONNX. Two TensorRT versions can also share a plugin defect. This comparison therefore narrows the investigation without certifying original-training parity.

## Accuracy remains poor in both environments

The table uses the first saved observation on the 16-frame test split at moderate difficulty. The same pinned KITTI evaluator and camera-visibility policy score every pipeline. Vehicle is evaluated explicitly as Car compatibility.

| Pipeline | Car BEV AP_R40 | Pedestrian BEV AP_R40 | Cyclist BEV AP_R40 | Moderate 3D true positives |
| --- | ---: | ---: | ---: | --- |
| Original frozen ROS baseline | 5.7516% | 0% | 0.02577% | 0 for all three classes |
| Independent TRT8 + NVIDIA NMS | 5.8349% | 0% | 0.02525% | 0 for all three classes |
| Independent TRT10 + NVIDIA NMS | 5.5349% | 0% | 0.02564% | 0 for all three classes |
| Independent TRT10 + our NMS | 5.5349% | 0% | 0.02564% | 0 for all three classes |

All three repeats in both runtimes have zero moderate 3D matches on both tuning and test splits. Test Car BEV AP ranges from 5.8049–5.8349% in TRT8 and 5.5268–5.5638% in TRT10. TRT8 matches 12 test cars in BEV, while TRT10 matches 11; frame 000910 accounts for the first-pass difference. That difference remains worth investigating, even though it cannot explain the broad failure common to both pipelines.

Twelve BEV-matched test cars in the first TRT8 pass have a median vertical error of **1.5288 m upward** and median 3D IoU about 0.0432. TRT10's 11 matched cars have a median upward error about1.5195 m. This reproduces the original ROS finding before ROS box conversion/display. It does not establish a universal shift: the matched subsets are small, and changing only displayed box heights would not fix poor horizontal detections or input voxelization.

## Numerical equality is not established

We match boxes one-to-one by class and all eight float components: XYZ, length/width/height, wrapped yaw and score. The diagnostic tolerance is 0.001 m for spatial components, 0.001 rad for yaw and 0.001 for score. It is not an agreed acceptance threshold. Duplicates cannot reuse one reference row.

| Comparison | Median observation match fraction |
| --- | ---: |
| TRT8 vs TRT10 raw candidates, first passes | 78.00% |
| TRT8 vs TRT10 final boxes, first passes | 75.70% |
| TRT8 repeated raw candidates | 79.41% |
| TRT10 repeated raw candidates | 78.30% |
| TRT8 repeated final boxes | 75.94% |
| TRT10 repeated final boxes | 75.10% |
| TRT10 adapter vs original frozen ROS boxes | 77.08% |

Within-runtime repeat rows compare repeat0 with repeats1/2, then take the median over 64 observations. Cross-runtime rows take the median over 32 frames. Fractions use the larger box count as denominator. Similar medians suggest shared variability, but they are not a statistical equivalence test or proof that the migration is numerically correct.

Raw counts varied in all 32 frames in both environments. The largest raw-count span was27 in TRT8 and28 in TRT10. Final counts varied in 28 TRT8 frames (maximum span 5) and27 TRT10 frames (maximum span 3). These are separate observations from the earlier longer live run.

## A shared capacity issue needs attention

The ONNX declares 10,000 voxels and 32 points per voxel. An audit found 12/32 original clouds above the voxel limit, with up to 15,180 occupied voxels. Every frame has crowded voxels: 33–585 voxels per frame exceed 32 points, accounting for 702–35,584 excess points. The initial descriptive audit uses double arithmetic and can differ at grid boundaries; the control helper also audits using float32 XY subtraction/division matching the kernel.

NVIDIA's published TRT8 and TRT10 voxel kernels select points using atomic counters. Their base-feature source writes coordinates using an incrementing pillar index without a visible check against the declared pillar limit. The plugin source declares the coordinate output for that limit. This raises an **internal tensor-bounds concern** when occupancy exceeds10,000. Source inspection is not proof of the exact machine instructions in the packaged libraries.

We made two tuning-only controls, frames 004804 and 007075. We retained the first 10,000 encountered voxels and first 32 points in each, discarded out-of-range points, and preserved all retained XYZI bits. There was no translation, scaling, new training or held-out-test adaptation. Three repeats per runtime added12 controlled inferences. Unique raw matching improved to about 99.60–99.80% for 004804 and 100% for 007075 at the 0.001 tolerance. Some differences remain, and this is a changed-input experiment rather than an accuracy improvement claim. It supports capacity/point selection as a contributor to repeat variation; it does not isolate one kernel or resolve training compatibility.

Compute Sanitizer 12.9 allocation memcheck actually ran on original and capped 004804 with TRT10, one execution each. Both exited 0 with zero reported allocation errors. Internal TensorRT tensors can share a larger allocation, so this does **not** establish tensor-bounds safety, race freedom, or complete GPU memory validation. The earlier CUDA 12.0 instrumentation failure remains a historical result.

Next establish the training/input contract, verify bounded voxelization and deterministic selection, and check decoder/feature behavior against an independent mathematical or training-framework reference. Do not install an empirical z shift or declare the weights the cause from this sample alone. Then evaluate any justified correction/model on untouched data with agreed targets.

## Reproduce the comparison

Use the prepared labeled dataset and frozen baseline described in [KITTI results](KITTI_ACCURACY_RESULTS.md). The validation detector must be running for collection so the helper can copy and verify its exact ONNX/engine. Host requirements are Docker/GPU integration, Python 3 and g++ for the unchanged CPU NMS/evaluator. ROS is needed only for the original baseline and live viewer. TensorRT libraries/headers for the reference adapters install inside their diagnostic images; host packages are not changed.

From the project folder:

```bash
python3 tools/kitti_reference.py build
python3 tools/kitti_reference.py collect
python3 tools/kitti_reference.py report
python3 tools/kitti_reference_repeat.py
python3 tools/kitti_voxel_control.py
python3 tools/kitti_reference_memcheck.py
```

The last two commands run additional tuning-only capacity and allocation-memory probes. The memory helper builds its optional image. For a new GPU, software/source identity, or independent experiment, use a fresh output directory with `--output` on the main/repeat tools and `--reference` on the control/memcheck tools. The collector's `--gpu` selects one physical GPU; both containers see it as CUDA device 0. The recorded diagnostic TensorRT8 stack was tested on this RTX 4060, not every GPU supported by the production TensorRT10 image.

Default results are under ignored `.recovery/accuracy/kitti-reference-v1`. Recipes freeze dataset, source, image, model, engine and GPU identities. Hash-verified raw observations are reused after interruption. Unindexed partial observations are quarantined rather than silently accepted. The TRT8 engine is promoted only after successful build; its hash is checked on reuse. Active collectors lock the output folder. Do not mix an engine from another TensorRT version/GPU. The deployment image and engine volume are not overwritten.

The collector expects a prepared baseline; it does not download KITTI data itself. Run `bash tools/kitti_accuracy.sh prepare` for labeled frames and `collect` for a new baseline when necessary. The sequence04 bag/video helper remains a separate unannotated demo.

## Inspect the reference in RViz

Keep the labeled KITTI live player running on domain 42. In one terminal:

```bash
source /opt/ros/jazzy/setup.bash
ROS_DOMAIN_ID=42 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
  python3 tools/kitti_reference_view.py
```

In another:

```bash
ROS_DOMAIN_ID=42 RVIZ_CONFIG="$PWD/rviz/kitti_reference.rviz" \
  bash tools/visualize.sh
```

Cyan boxes are frozen first-pass TRT8 reference predictions; green boxes are calibrated annotations; the Detections display shows current live TRT10 results with its existing class colors. The overlay selects saved results by exact cloud bytes and copies the current cloud header. It does not run another detector or alter measurements. Toggle displays to see overlap. A global TF warning can remain on this sensor-only stream; points/boxes share `velodyne` and rendered successfully.

Ctrl+C stops the overlay or viewer in its terminal. `python3 tools/kitti_reference_view.py --stop` signals only the overlay whose PID/start identity it recorded; close the RViz window separately. Existing `kitti_accuracy.sh stop` handles its validation detector/player. Unrelated containers are preserved. The overlay, original live player/detector and reference RViz window were left running after verification.

## Files and recovery

| File | Purpose |
| --- | --- |
| `docker/reference/Dockerfile` | Independent Ubuntu22.04/TRT8.6/CUDA 12.0 image and pinned unchanged NVIDIA NMS |
| `docker/reference/Dockerfile.trt10` | Separate V3 adapter using the deployment libraries |
| `docker/reference/runner.cpp` | Count-checked lossless candidate collection, reusable buffers, V2/V3 paths |
| `docker/reference/nms_driver.cpp` | Identical-candidate adapter for either NMS implementation |
| `docker/REFERENCE_MEMCHECK.Dockerfile` | Optional CUDA 12.9 allocation-check image |
| `tools/kitti_reference.py` | Build/collect/report, identities, immutable inputs, locking and recovery |
| `tools/kitti_reference_repeat.py` | Score each saved repeat and measure vertical errors |
| `tools/kitti_voxel_control.py` | Float32 capacity audit and two unchanged-bit tuning controls |
| `tools/kitti_reference_memcheck.py` | Real allocation instrumentation, never reusing an output as a test |
| `tools/kitti_reference_view.py`, `rviz/kitti_reference.rviz` | Exact-cloud reference overlay alongside live output/GT |
| `tests/test_kitti_reference.py` | Unique matching, float output rejection and deterministic-cap fixtures |
| `config/kitti_reference_inventory.json` | Exact measured identities, results and immutable evidence hashes |

Nine focused controls and 50 total Python tests passed. Exact collection hashes, comparisons, all-repeat scores, controls, logs and actual RViz screenshot are indexed by the inventory. Dataset, engines, outputs, downloaded source and images are ignored and excluded from source checkpoints; retain independent backups. These source changes are local until committed/pushed. No application runtime rebuild, registry publication or retraining occurred.

Primary sources: [NVIDIA sample](https://github.com/NVIDIA-TAO/tao_toolkit_recipes/tree/a540badc47812a17a94e924b537d49ad3969b5a8/tao_pointpillars/tensorrt_sample), [TRT8 voxel kernel](https://github.com/NVIDIA/TensorRT/blob/a0215c1a16c6413c7ac566a498871a4fa36f6f62/plugin/common/kernels/voxelGeneratorKernels.cu), [TRT8 voxel plugin](https://github.com/NVIDIA/TensorRT/blob/a0215c1a16c6413c7ac566a498871a4fa36f6f62/plugin/voxelGeneratorPlugin/voxelGenerator.cpp), [TRT10 voxel kernel](https://github.com/NVIDIA/TensorRT/blob/d0faf303ba766f20cd9fd8c413a112fc2e5a397b/plugin/common/kernels/voxelGeneratorKernels.cu), [NVIDIA input-domain guidance](https://github.com/NVIDIA-AI-IOT/ros2_tao_pointpillars), [KITTI protocol](https://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d).
