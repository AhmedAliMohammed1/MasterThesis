# Preparing labeled KITTI scenarios

This is the first implementation step in the [model validation plan](MODEL_VALIDATION_PLAN.md). It prepares matched point clouds, object annotations, calibration and camera images. It does not run inference or calculate accuracy. The earlier sequence04 bag and camera video remain useful integration examples, but have no object annotations in this project.

From the project folder, run:

```bash
python3 tools/prepare_kitti_validation.py \
  --output ../datasets/kitti_object_diagnostic_v1
```

Python 3 and an internet connection are sufficient. No ROS, GPU, TensorRT, pip packages or host installation is needed for preparation. The default selects 16 tuning frames and 16 test frames. On the current computer, the output is `/media/ae/New Volume/datasets/kitti_object_diagnostic_v1`.

The tool reads all 7,481 public training annotations before selecting frames. It downloads the small label and development-kit archives, then uses verified byte ranges for selected calibration, cloud and image members. It refuses servers that ignore ranges rather than fetching the full 29 GB cloud archive. The source endpoints, object ETags and sizes are pinned in [kitti_sources.json](../config/kitti_sources.json); small archives also have pinned SHA256 digests. Review that inventory explicitly if the publisher changes an object.

Use the [official KITTI dataset page](https://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d) for dataset terms, attribution, access and format information. If public endpoints become unavailable, obtain the official ZIP files through its download process. Put `data_object_label_2.zip`, `data_object_calib.zip`, `data_object_velodyne.zip`, `data_object_image_2.zip`, and `devkit_object.zip` together, then run:

```bash
python3 tools/prepare_kitti_validation.py \
  --output ../datasets/kitti_object_offline_v1 \
  --archives-dir "$HOME/Downloads/kitti"
```

Offline archives must have the pinned sizes. The tool records their member-directory identities and selected-file hashes, and verifies selected members against ZIP CRCs. Size and CRC alone do not authenticate a publisher; offline input is recorded as user-provided. Online large archives are bound to HTTPS endpoints, ETags and sizes, not claimed to have independently verified whole-archive SHA256. An S3 multipart ETag is an object identity, not a SHA256 digest.

## How the scenarios and splits are chosen

Selection uses annotations before any predictions are examined. The seed is `pp-kitti-diagnostic-v1`, and the algorithm is `drive-disjoint-annotation-coverage-v1`.

The official development kit maps training frame IDs to raw recording date, drive and frame. The tool applies KITTI's one-based permutation, then partitions entire recording drives using a seeded SHA256. A drive cannot occur in both tuning and test. Within each partition, deterministic selection first covers missing scenario buckets, then balances repeated coverage with preference for rarer buckets. Hashes settle ties.

Buckets identify original KITTI Car/Pedestrian/Cyclist labels, camera depth below 20 m or at least 40 m, one relevant labeled object, at least five relevant labeled objects, partial/large occlusion, truncation above 0.15, and difficulty categories. “Isolated” refers to relevant annotations, not a guarantee that the scene contains no other object. Difficulty buckets are preparation metadata; the official evaluation rules must still be implemented separately. A frame can have several buckets, so their counts overlap.

The manifest reports missing buckets explicitly and requires all three relevant classes in each split. The current 32 frames cover every configured bucket in both splits. KITTI does not provide representative coverage of every weather or lighting condition. This deliberately varied sample is for diagnosing mistakes, not an unbiased estimate of overall accuracy. We also do not have NVIDIA's training frame list, so pretrained-model overlap remains unknown.

To prepare a larger selection, use a **new** destination. For example:

```bash
python3 tools/prepare_kitti_validation.py \
  --frames-per-split 100 \
  --output ../datasets/kitti_object_diagnostic_200_v1
```

The same drive partition applies with the default seed, and selections are deterministic. Increasing the count may include existing diagnostic frames, so this command does not automatically create a fresh independent acceptance set. Freeze the final evaluation design before tuning. A changed count, seed, source inventory, model geometry or implementation identity cannot overwrite an existing frozen selection.

## What is saved

| Path inside the output folder | Purpose |
|---|---|
| `selection.json` | Frozen cohort hash, seed, algorithm, recording mapping, split frame IDs, scenario coverage and preparation recipe |
| `training/velodyne/*.bin` | Original little-endian float32 XYZI clouds |
| `training/label_2/*.txt` | Original KITTI camera-coordinate annotations, including DontCare |
| `training/calib/*.txt` | Matching projection, rectification and LiDAR-to-camera calibration |
| `training/image_2/*.png` | Matching left color camera images |
| `annotations_lidar/*.json` | Original annotations plus transformed center, dimensions, full orientation, eight corners, projection and range coverage; point-cloud audit and asset hashes |
| `manifest.json` | Completed dataset identity, source metadata, file hashes, split membership and summary |
| `.cache/` | Small pinned archives retained for recovery |

The folder receives its own `.gitignore`, and the default location is outside the source checkout. These assets stay out of Git and source checkpoints. Back up the manifest together with the assets if you want to reproduce a result on another computer. Camera files are retained for a later projected-box review; this patch does not start RViz or play a bag.

## Coordinate conversion

KITTI stores dimensions as height, width and length, and location at the bottom center in rectified-camera coordinates. The converter first subtracts half the height from camera y to obtain the geometric center. It then inverts the complete `R0_rect * Tr_velo_to_cam` transform. It keeps the translation and rectification rotation rather than assuming an ideal camera mounting.

The resulting local box axes are length, width and upward height. The report retains the full orientation matrix and all eight corners. `yaw_lidar_diagnostic` describes the projected heading only; reconstructing the box from that yaw alone would lose calibration tilt. No yaw-only approximation is used for the saved ground-truth geometry. Projection uses the matching P2 matrix, and corners behind the camera have no image projection.

DontCare stays an image ignore region and has no invented 3D box. Original class names remain unchanged. NVIDIA's Vehicle output is broader than KITTI Car; model-to-KITTI mapping and evaluator ignore/visibility rules remain pending. These reports do not silently merge Van into Car or claim an official score.

The cloud audit records point count, nonfinite values, intensity bounds, engine-capacity compatibility, and finite points inside the exact export range. Object reports separately record center and all-corner coverage. No point filtering, intensity rescaling, calibration change or z shift is applied to the downloaded clouds.

## Recorded preparation result

On 3 October 2026, preparation completed for 32 frames: 16 tuning and 16 test. Selected assets total 86,561,388 bytes, before reports and cache. Initial range traffic was about 187 MB, including small archives; subsequent runs still read ZIP directory metadata but reuse verified completed assets. The full large archives were not downloaded.

The annotations contain 137 Car, 108 Pedestrian and 48 Cyclist objects, plus 10 Van, four Person_sitting and 47 DontCare regions. Clouds contain 108,943–124,047 points, below the 204,800 capacity. No nonfinite cloud points or intensity values outside [0,1] were accepted.

| Original class | Labeled boxes | Centers inside model range | All corners inside model range |
|---|---:|---:|---:|
| Car | 137 | 126 | 35 |
| Pedestrian | 108 | 104 | 28 |
| Cyclist | 48 | 48 | 17 |

These are geometric coverage counts, not detected objects. They support investigating the model's range and dataset differences before judging accuracy. A partially out-of-range box can still be detected; these counts neither prove nor quantify detection failure. Every original annotation is retained.

The final run identity, split hashes and logs are indexed in [kitti_validation_inventory.json](../config/kitti_validation_inventory.json). Evidence is local and ignored; retain independent backups when sharing the source.

## Recovery and checks

After an interruption, run the **same preparation command** again. The file lock prevents simultaneous preparation into one folder. Selected members are bounded, streamed into `.part` files, checked against CRC/size and atomically promoted. Complete pending members and small archives can be reused. Incomplete pending members restart individually; completed frames are preserved. The tool recomputes and checks the frozen selection before proceeding, and writes the final manifest only after all selected frames pass preparation checks.

A corrupt completed asset or changed frozen report causes an explicit failure and is preserved for inspection. Do not overwrite it blindly. Compare the manifest/hash, preserve the suspect file, and remove only the identified damaged generated asset before retrying. A partially completed folder with no `manifest.json` is not a completed dataset. Directory contents and source checkpoints do not protect against disk loss.

Run the focused tests from the source folder:

```bash
python3 -m unittest discover -s tests -p 'test_kitti_validation.py' -v
python3 -m unittest discover -s tests -p 'test_kitti_demo.py' -v
```

The calibration tests use independently known centers, corners and headings, including a translated mount and nontrivial rectification. Other tests exercise malformed labels/calibration, image header integrity, point layout/range/capacity, interrupted offline preparation, completed pending promotion, preserved corruption, frozen recipes, source hash failures and disjoint drive splits. The existing HTTP fixture checks exact ranges, source pinning and truncated/ignored ranges.

Next export predictions for these frozen frames, establish an independent same-model reference, freeze class/visibility/ignore rules, and evaluate accuracy. No detection score, accuracy pass or runtime change is claimed by dataset preparation.


## Measurement update: 3 October 2026

The first labeled 32-frame diagnostic baseline is now measured. The 16-frame test split has zero moderate 3D matches; moderate BEV AP_R40 is Car 5.75%, Pedestrian 0%, Cyclist 0.0258%. Vehicle is explicitly mapped to Car compatibility. The evaluator's exact/missing/duplicate controls passed, and 41 total Python tests passed. Green calibrated ground truth and live predictions render together in RViz on domain 42. First-pass detections are frozen; repeated counts vary and full independent original-model parity remains pending. Read [accuracy results and commands](KITTI_ACCURACY_RESULTS.md) and [inventory](../config/kitti_accuracy_inventory.json). Earlier “not measured” statements describe preparation or the initial investigation, not this new baseline. Accuracy acceptance remains unmet.


## Independent reference update: 3 October 2026

A separate TensorRT8.6 engine for the exact ONNX reproduced the poor KITTI baseline and approximately1.53m upward car error. Three repeats per runtime (192 raw inferences) still produced zero moderate 3D matches in both runtimes. NVIDIA's unchanged NMS and our NMS selected identical boxes on all192 same-candidate observations. Strict numerical parity remains unmet: both runtimes vary, and12 frames exceed the export's10,000-voxel limit. Two tuning-only capacity controls improved repeat matching to roughly99.6–100%; no production adaptation was installed. Two actual CUDA12.9 allocation probes reported zero errors, which does not clear the internal tensor-bounds concern or complete GPU memory validation. Read [independent comparison](MODEL_REFERENCE_COMPARISON.md) for commands, results, source evidence and limits. Pretrained weights alone are not established as the cause; bounded voxelization and the original input/training contract are next.
