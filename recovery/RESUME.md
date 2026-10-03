# Resume pp_infer work after interrupted credit, context or tooling

Open this repository: `/media/ae/New Volume/MasterThesis`.

The user authorized implementation on 2026-10-01. W02 CPU foundations and W03 local ROS adapters are implemented; W04/W05 runtime source migration builds/links against extracted TensorRT 10.16.1.11 and passes synthetic GPU smoke checks; reference semantics, memory/failure checks and W06 remain pending; read PROGRESS.md/tasks.json and the latest checkpoint for verification and remaining blockers. Docker packaging is implemented and verified with synthetic GPU/ROS checks; see docker/README.md and config/docker_inventory.json. Continue using the protocol below, preserving existing work.

The A-to-Z implementation/deployment guide is `docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex`; README now describes the Jazzy workflow. All current build instructions now use colcon; reduced CPU, sanitized CPU and ROS builds/tests passed. Its commands passed syntax/link checks and its synthetic container command passed in isolated ROS domain 91. Built-in LaTeX compilation remains unverified: the original attempt could not retrieve its TeX bundle, and attempts after the folder move report that the LaTeX sandbox connection closed before parsing source. Preserve the source and retry with the built-in compiler when available; do not install a terminal TeX distribution for this task.

## Current deployment and moved checkout

The user moved the checkout to `/media/ae/New Volume/MasterThesis` on 2026-10-02. Quote this path. Docker still uses its own host storage filesystem; moving the project does not move Docker images/cache. Old native build/install outputs contain stale absolute paths; select fresh directories when rebuilding native code. Historical logs/inventories retain their original paths as evidence.

`sudo bash tools/deploy.sh` builds published GitHub source, downloads and verifies the pinned NGC model, installs pinned TensorRT shared runtime/plugins/tools/headers, builds/tests with colcon, then launches the GPU node. Source edits must be pushed before they are included. No local SDK/model inputs are needed. Keep large assets ignored. See the latest progress entry and image inventory for verified build/GPU evidence and current container state. W09 remains in progress for full operational/CI acceptance.

## Historical real-bag viewer state (inspect current processes)

The KITTI sequence04 bag playback (`pointpillars-bag`) and inference (`pointpillars`) passed 25 matched frames inside Docker and another25 on the host with UDPv4. `bash tools/visualize.sh` opened a live RViz view of points and Detection3DArray boxes; the GUI was left running. Before starting another viewer, inspect current processes/windows. Source/configuration and optional plugin setup are documented in README. Numeric box colors are not semantic class labels; no accuracy validation was claimed. A global TF warning from sensor-only playback is recorded; the shared `velodyne` frame renders successfully. Do not add assumed world transforms.

`config/visualization_inventory.json` indexes exact reports, screenshot, plugin version/hash and verification commands. The local plugin, diagnostic script and evidence under `.recovery` are excluded from snapshots; back them up separately. W07 visualization substep is delivered but full launch/QoS/metrics acceptance remains unfinished, as does W06. The user subsequently published visualization and bag/video source at `dd687da7f42b4dc8fb53370be4a7c26635bc6e95`; earlier uncommitted statements are historical. The latest LaTeX compile again failed before parsing because its uncached bundle could not be downloaded.

## Current sample-data helper

`bash tools/rosbag_demo.sh` now prepares the pinned KITTI bag and matching drive camera MP4, then starts/reuses matching LiDAR playback. `prepare` saves assets only; `stop` stops only a helper-labeled player. Defaults use the existing `/media/ae/New Volume/rosbags/kitti04` folder beside this checkout. The earlier manually started player was intentionally preserved during validation. At the first history snapshot, the user had restarted the player through the helper and its ownership label was present; inspect actual containers before acting. Camera clip and timestamps are prepared; repeat runs verified cache reuse. A separate Docker image installs preparation libraries without host changes. Asset directories contain their own ignore file; assets/logs are excluded from checkpoints.

`config/demo_inventory.json` records provenance, source/clip hashes, 285 camera frames, 283 LiDAR frames, eight passing recovery tests, actual isolated-domain playback/stop and full video decode. Camera starts about0.210s before LiDAR and the video is not synchronized or annotated ground truth; do not claim accuracy. Model contract, W06 and remaining W07 acceptance are still incomplete. The bag/video and RViz changes are now published at dd687da; this history-documentation patch remains local. The latest LaTeX attempt again failed before parsing on the unavailable compiler bundle.

## Complete project and discussion history

Read `docs/PROJECT_HISTORY_AND_DECISION_RECORD.md` for the natural-language account of the architecture, migration, installation choices, Docker evolution, relocation, Git authentication advice, real-bag validation, RViz, camera video and every changed implementation file. `docs/CHAT_DISCUSSION_RECORD.md` preserves the visible discussion through the latest continuation. README links both documents. Historical inventory paths, image identities and publication states describe their original checks; do not treat them as fresh observations.

The first history-writing turn hit the usage limit. On continuation, the project volume was unmounted; normal disk-service mounting reconnected it. The saved chat record was retained, and the narrative draft was recovered from this thread's local session record and saved before further edits. A checkpoint should preserve actual files rather than rely on tool-session storage. The history is Markdown and needs no LaTeX compiler.

## W01 KITTI accuracy work started

The user chose varied labeled KITTI scenarios first, then their own sensor recordings when available. Read `docs/MODEL_VALIDATION_PLAN.md` and partial `config/model_contract.json`. The exact NGC version label/model hashes now verify IDs 0 Vehicle, 1 Pedestrian, 2 Cyclist. NVIDIA decoder source supports center-based boxes; normalized XYZI input is documented and fits the first three bag clouds. Earlier unresolved class-order statements are historical. Runtime config still uses smoke labels; numerical/calibration fixtures and independent reference/accuracy checks are not complete.

The preparation/calibration substep is now delivered; see the 3 October update below. Next implement prediction export and independent exact-model parity, then evaluator rules and baseline accuracy. Existing bag/video have no object annotations; do not call them accuracy data or silently change z/intensity because many raw points lie outside the export range. Freeze class mapping/visibility/evaluator/splits and define acceptance targets. W01 is now in progress; the contract remains partial and is not runtime enforcement. Raw evidence is ignored and needs its own backup.

## Available now

Requirements: Python 3 and Git. No ROS, CUDA, GPU, model access or paid API is needed for checkpoint/status commands. Run from the repository root:

```bash
cd '/media/ae/New Volume/MasterThesis'
python3 tools/recovery.py status
```

Create a checkpoint at the beginning of a work unit, after coherent edits, after tests, and before a long-running command. Example **for a future W02 implementation session**:

```bash
python3 tools/recovery.py checkpoint \
  --task W02 --state in-progress \
  --next 'Extract CPU geometry from CUDA includes, then run its focused tests.' \
  --evidence 'Not tested yet; see recovery/PROGRESS.md.'
```

After tests actually pass, update progress/ledger first and record their exact command, exit code and saved log path. Then use `--state verified` with evidence. Use `--state blocked` with the missing prerequisite and unblock action when needed. The helper records assertions; it does not run tests or enforce milestone prerequisites.

The helper is run explicitly by the agent or a person. There is no background watcher. A successful checkpoint is an immutable local directory under `.recovery/checkpoints/`; incomplete temporary directories are not accepted as completed checkpoints. Status validates saved content and compares the current tree to the latest completed snapshot. It never checks out, resets, stages, commits or restores files. Save independent backups if disk-loss recovery is required.

Source snapshots include tracked and nonignored untracked eligible UTF-8 text files. Defaults cap files at 1 MiB each, total source snapshots at 16 MiB and each patch at 32 MiB. Build outputs, `.recovery`, model/bag/media binaries, likely credential paths and oversized files are excluded as reported in the manifest. Symlinks are recorded as links, not followed. Ignored artifacts and files outside the repository require their own backup/location/hash records. Exclusions are deliberately not a full-machine backup or a guarantee of detecting every secret; do not put secrets in source or evidence text. Inspect exclusions before relying on a snapshot. Local test logs under `.recovery` remain on disk but are not recursively copied into snapshots.

## Recovery sequence

1. Read `IMPLEMENTATION_ARCHITECTURE.md`, `recovery/tasks.json` and `recovery/PROGRESS.md`. Read repository instructions if present. Do not restart the architecture analysis from scratch.
2. Run `python3 tools/recovery.py status` and inspect the printed checkpoint manifest, integrity result and current drift. Also inspect `git status --short`, `git diff` and `git diff --cached`; account for untracked files separately. A changed HEAD, changed file, failed integrity check or mismatched evidence invalidates any assumption that old tests cover current work.
3. Treat `in-progress` and `blocked` as unfinished. A `verified` label still needs its evidence and relevant hashes. Inspect excluded files relevant to the task. If status reports a corrupt checkpoint, inspect earlier complete checkpoints and their manifests; do not silently trust a fallback or overwrite current files.
4. Check whether an interrupted build, benchmark or engine-generation process is still running before launching another. Inspect outputs before retrying any install/build/promotion command. Keep incomplete engine outputs separate from validated artifacts.
5. Preserve current work. If file recovery is necessary, compare the snapshot file to the working file and recover selected content manually after reviewing the diff. Saved patches describe staged/unstaged state against their recorded base; never blindly apply both onto an already modified checkout. The original Git index is never changed by this helper.
6. Select the interrupted substep first, or the earliest ready task whose dependencies are satisfied. One editor per shared file and one ledger writer. If GPU prerequisites remain blocked, continue independent CPU/ROS work and retain that blocker.
7. Write an `in-progress` checkpoint **before editing**. Complete one coherent patch, run the smallest meaningful affected checks, update progress/ledger, and checkpoint again. Re-run downstream checks when shared contracts change; do not rerun expensive unaffected suites repeatedly.
8. Report what changed, which checks actually passed, what remains blocked and the next action. Never convert absent GPU evidence into a pass.

## Copy into the next chat when ready to implement

> Continue implementation in `/media/ae/New Volume/MasterThesis` using `IMPLEMENTATION_ARCHITECTURE.md`. First read `recovery/RESUME.md`, `recovery/PROGRESS.md` and `recovery/tasks.json`, run `python3 tools/recovery.py status`, and reconcile the actual working tree with the last completed checkpoint. Preserve all existing changes. Resume the interrupted substep or the earliest unblocked task; do not repeat completed work without a reason. Checkpoint before and after each coherent edit/test. Record exact verification evidence and remaining GPU/model blockers. Do not claim inference or real-time performance is verified without target-hardware evidence.

If the old chat is available, resuming it retains conversational context; these files also support a fresh chat. Availability/credits must first permit model work. The local recovery helper cannot increase quota or automatically continue the model after a stop.


## Latest continuation: W01.2 prepared labeled data (2026-10-03)

Read `docs/KITTI_VALIDATION_DATA.md` and `config/kitti_validation_inventory.json`. The 32 matched KITTI frames are at `/media/ae/New Volume/datasets/kitti_object_diagnostic_v1`. Final manifest/selection hashes, exact frame IDs, source pins, recipe and logs are indexed. The 16+16 split is annotation-selected and raw-recording-drive-disjoint; all configured buckets are present. Calibrated ground-truth reports preserve full orientation/corners, original classes and DontCare. Fifteen focused and35 total Python tests passed, along with real preparation and repeat reuse. This is data preparation, not inference parity or accuracy acceptance.

To resume preparation, run `python3 tools/prepare_kitti_validation.py --output ../datasets/kitti_object_diagnostic_v1` from this checkout. The identical code/recipe verifies and reuses assets; a changed recipe requires a new output directory. Do not overwrite frozen files. Independently back up the dataset and ignored verification logs; checkpoints preserve source/inventory rather than large data. First pre-review manifests retained with `.initial-pre-review` suffix are historical, not the final manifests.

Next implement prediction export for frozen frames, an independent exact-model runtime/reference with geometry-based matching, then fixed class/visibility/ignore/evaluator rules and accuracy baseline. Keep diagnostic/tuning changes away from the test split. Do not infer detection failure or invent a z shift from partial model-range box coverage. Runtime contract enforcement and label configuration remain separate unfinished work. No runtime or Docker source/image changed in this substep. These edits are uncommitted; Docker still pulls published Git, so a build will not include local validation tools until the user publishes them.


## Latest: W01.3 accuracy measured, poor baseline (3 October 2026)

Read docs/KITTI_ACCURACY_RESULTS.md and config/kitti_accuracy_inventory.json first. The32 frozen frames have real ROS outputs in .recovery/accuracy/kitti-baseline-v1, with first observations preserved and policy/report hashes. Moderate16-frame test3D TP=0 for Car/Pedestrian/Cyclist. BEV AP_R40 is5.75%/0%/0.0258%, with explicit Vehicle->Car compatibility mapping. Forty-one tests and exact/missing/duplicate metric controls passed; final report reproduced. The12 BEV-matched cars have median upward center error1.529m. Live counts varied; trtexec probe is only candidate consistency, not full independent original-model parity. Accuracy acceptance is not achieved.

Detector pointpillars-validation, kitti_validation_player and RViz were left running on domain42, topics /kitti/point_cloud, /kitti/predictions, /kitti/ground_truth and framevelodyne. Green boxes are calibrated GT. Inspect actual processes first. bash tools/kitti_accuracy.sh report reuses the frozen run; live/collect refuse another active player. bash tools/kitti_accuracy.sh stop checks recorded task-owned container/process identities before stopping them. Ownership records are under the result folder, not source snapshots. If missing/stale, inspect and stop only the intended resources. Other containers/apps are preserved.

Next resolve original-model input/vertical contract, plugin/runtime reference parity and numerical repeatability before guessing any z shift. Define a larger untouched acceptance split/targets; the diagnostic test set has now been inspected. Keep first observations, outputs and policy immutable. Existing source/tool hashes bind this measured implementation; changed identities require a new result directory. Data/evidence are ignored and need independent backup. The built-in LaTeX compiler failed before parsing because its bundle could not be downloaded; source updated in place, PDF unverified. All documentation has dated status/findings; historical addenda do not rewrite old observations. No commit/push or image rebuild performed.

## W01.4 independent comparison delivered: 3 October 2026

Read docs/MODEL_REFERENCE_COMPARISON.md and config/kitti_reference_inventory.json first. Outputs are ignored .recovery/accuracy/kitti-reference-v1: frozen recipe/collection, lossless raw/final observations, all-repeat scores, capacity controls, memory probes and source/evidence hashes. The TRT8 compatibility reference reproduced poor accuracy and elevated centers. All192 same-raw NMS observations agree; exact training/numerical parity and accuracy acceptance remain unmet. Two tuning capacity controls improve repeat matching to roughly99.6–100%;12 original frames exceed the export's voxel limit. Source raises internal tensor-bounds concern; two zero-error allocation probes do not clear it.

Next verify bounded voxelization and original input/training/decoder behavior before blaming weights or installing an empirical shift. Production runtime/source/image/engine and original ROS baseline remain unchanged. W01 is in progress; the comparison substep is delivered, not accuracy acceptance. Source edits remain local/unpublished.50 Python tests passed. Existing LaTeX updated in place; built-in compilation still cannot obtain uncached bundle, PDF unverified.

The original validation detector/player plus reference overlay and RViz were left running on domain42. Inspect actual processes/ownership before stopping or duplicating them. Overlay owner is kitti-reference-v1/overlay-owner.json; python3 tools/kitti_reference_view.py --stop validates PID/start identity. Close reference RViz separately. Original kitti_accuracy.sh stop handles its detector/player; preserve unrelated YOLO. Large evidence is outside source snapshots and needs independent backup. Same frozen identities reuse validated raw files; changed code/image/GPU needs a fresh output directory. New source commands and source-level concerns are documented; older “reference unfinished” statements refer to training parity or historical phases, not absence of this compatibility comparison.
