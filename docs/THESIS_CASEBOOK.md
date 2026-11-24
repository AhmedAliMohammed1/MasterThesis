# Illustrated problem and solution casebook

Reviewed 9 November 2026. This is the problem-and-solution appendix of the existing [thesis draft](THESIS_DRAFT.tex), also available in [Markdown](THESIS_DRAFT.md).

Each case answers five questions: what happened, why it happened, what small steps were taken, what checked the result, and what remains open. A successful software check is kept separate from a successful accuracy result.

Each problem has an editable table showing the observed condition and the recorded outcome. Selected flowcharts explain validation, startup, shutdown, transport and evaluation. These diagrams explain the recorded implementation or method; they are not screenshots of an experiment. New controlled checks use isolated fixtures, and a mock Docker service does not mean a real container failed. Preserved logs, source reviews and unresolved conditions remain clearly labeled. Original RViz captures and two genuine terminal demonstrations are retained where they help explain the evidence.

Unsafe physical failures were not recreated: no disk was filled, no display driver was deliberately broken, and no source bag or annotation was damaged. Where only supplied-log summaries survive, that is stated. The six new raw-signal/reflectivity GPU demonstrations are separate from the frozen 1,120-observation accuracy/numerical study; they do not add independent labeled scenes or establish accuracy.


## J01. Old OS, ROS and build settings

**What happened:** The old build combined C++14 settings with an explicit C++11 flag, old CUDA paths and a Foxy-era dependency layout.

**Why:** Those settings described another software stack. The migration made CPU tests independent and declared ROS and GPU dependencies only for targets that need them.

**Small steps:**

1. Read the old CMake file without changing the checkout.
2. Select C++17 and explicit target dependencies.
3. Configure the CPU-only build with runtime and ROS adapter disabled.
4. Build and run the geometry and output-contract controls before enabling ROS/GPU targets.

**Check:** A fresh isolated current-source CPU configuration and build succeeded on 9 November; both test executables passed. Legacy CMake was inspected through git show 2301135:CMakeLists.txt.

**What remains open:** This does not validate a fresh host installation, another GPU or exact inference parity.

**Evidence type:** Source-based explanation.

| What was observed | Recorded outcome |
| --- | --- |
| Old source mixes C++14 and C++11 settings and hardcoded CUDA paths. | Current CPU-only targets configure and build independently; focused checks pass. |

**Evidence files:** `CMakeLists.txt`, `PROJECT_REVIEW_AND_UPDATE_PLAN.md`, `docs/PROJECT_HISTORY_AND_DECISION_RECORD.md`, `.recovery/verification/thesis-evidence-2026-11-09/migration/cpu-configure.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/cpu-build.log`.


## J02. Old include and ROS message schema

**What happened:** The source included a nonexistent local point_cloud2_iterator.hpp and wrote obsolete hypothesis fields.

**Why:** Jazzy stores class ID and score inside hypothesis. Removing the unused include is separate from correctly translating box and header data.

**Small steps:**

1. Remove the unused nonexistent include.
2. Construct the current nested Jazzy hypothesis fields.
3. Copy the source header to the array and each detection.
4. Check dimensions, pose and class ID using a small known box.

**Check:** A safe compiler-only control of the missing include exited 1 with a real fatal error. The freshly compiled current-code probe then emitted class_id=1, source_frame=lidar and the fixture timestamp; the ROS data suite passed.

**What remains open:** The old full node was not executed; this is a controlled include failure and a current-schema control.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Compiler-only old-include control: the referenced header cannot be found. | Current production validator constructs Jazzy nested hypotheses and preserves the fixture header. |

**Evidence files:** `PROJECT_REVIEW_AND_UPDATE_PLAN.md`, `src/pointcloud_adapter.cpp`, `tests/ros/test_ros_adapter.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J02-original-include-control.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`.


## J03. Malformed, oversized and nonfinite clouds

**What happened:** Malformed rows, missing fields, excessive point counts or NaNs could make point-cloud conversion unsafe or misleading.

**Why:** A PointCloud2 message has a binary layout. Validate dimensions, strides, field bounds and capacity before conversion; is_dense alone is not proof that points are finite.

**Small steps:**

1. Check width, height, point_step, row_step and exact data length.
2. Require nonoverlapping scalar little-endian FLOAT32 x/y/z/intensity fields.
3. Reject point or byte capacity overflow before allocation.
4. Remove nonfinite points even when is_dense is true.
5. Require a finite positive intensity divisor and clear stale packed output on failure.

**Check:** The fresh production-code probe printed exact layout, capacity, missing-field, endian and divisor rejections. Repairing row_step accepted four points; inserting one NaN packed three. All 11 existing ROS data controls passed.

**What remains open:** Finite all-zero invalid returns are not removed here. Total point limits do not enforce the internal pillar limits.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Invalid row stride, point capacity, field layout, byte order or divisor is rejected. | Correct padded rows pack four points; one NaN reduces the packed cloud to three. |

**How this part works:**

```mermaid
flowchart TD
    A["Receive PointCloud2"] --> B{"Layout, byte bounds and point capacity valid?"}
    B -->|No| C["Reject cloud and clear packed output"]
    B -->|Yes| D{"Intensity divisor finite and positive?"}
    D -->|No| C
    D -->|Yes| E["Pack finite XYZI points and support valid row padding"]
    E --> F{"Any finite points remain?"}
    F -->|No| G["Skip GPU inference for the empty valid cloud"]
    F -->|Yes| H["Pass packed points to inference"]
```

![J03: original capture or live demonstration](figures/thesis/J03-live-validator-terminal.png)

Actual new terminal capture: the current C++ validator rejects an artificial malformed row and accepts corrected padding. Other invalid-layout controls are shown. No GPU or ROS node is created.

**Evidence files:** `src/pointcloud_adapter.cpp`, `include/pp_infer/model_contract.hpp`, `tests/ros/test_ros_adapter.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/ros-data.log`.


## J04. Degenerate overlap and unstable filtering

**What happened:** Degenerate boxes, unstable overlap calculations or stale outputs could undermine filtering.

**Why:** Rotated IoU needs robust geometry handling. Suppression should reject invalid configuration, preserve deterministic score ties and replace previous-frame output even for an empty frame.

**Small steps:**

1. Validate finite centers, dimensions and yaw; require positive dimensions.
2. Compute rotated overlap using bounded polygon clipping.
3. Validate IoU threshold and top-N before suppression.
4. Use stable score ordering and clear the output on every attempt.
5. Check touching, contained, rotated, degenerate and random boxes.

**Check:** The current-source probe returned IoU=0 for zero-length geometry, rejected a negative NMS threshold and changed a one-box output to zero on an empty frame. Fresh geometry tests passed 15 cases including 2,000 randomized comparisons.

**What remains open:** Robust suppression does not move inaccurate boxes or establish detector accuracy.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Negative NMS threshold is rejected; zero-length geometry safely yields zero overlap. | Valid suppression returns one box; a subsequent empty input clears it. |

**Evidence files:** `src/postprocess.cpp`, `tests/core/test_postprocess.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/cpu-geometry.log`.


## J05. Cross-class suppression policy

**What happened:** Two overlapping predictions with different class IDs can suppress each other.

**Why:** Production NMS intentionally remains class-agnostic. The CPU core has a class-aware option, but it is not the current production policy or a demonstrated accuracy improvement.

**Small steps:**

1. Create two boxes with identical footprints and different class IDs.
2. Run the current default NMS and record the retained count.
3. Run the core class-aware option on the same candidates.
4. Keep the production policy explicit; evaluate a proposed change on tuning data before deployment.

**Check:** The fresh current-source probe retained one box with the default and two with the class-aware option; the existing same-class/cross-class regression passed.

**What remains open:** No production policy was changed, and no class-aware accuracy advantage has been measured.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Default class-agnostic NMS keeps one of two overlapping boxes with different classes. | The diagnostic core class-aware option keeps both; production was not changed. |

**Evidence files:** `src/postprocess.cpp`, `tests/core/test_postprocess.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`.


## J06. Session and usage interruption

**What happened:** A usage/session interruption can lose the next action and confuse what was actually tested.

**Why:** Recovery saves eligible source, hashes, separate patches and a handoff. Its evidence text is caller-reported, not a substitute for test execution.

**Small steps:**

1. Save a checkpoint before a coherent change or long operation.
2. Record the next action and actual verification commands.
3. On return, read RESUME, PROGRESS and the task ledger.
4. Run recovery status and inspect Git drift before continuing.
5. Back up ignored large artifacts separately.

**Check:** All 12 recovery tests passed in isolated temporary repositories. A deliberate corruption in a temporary checkpoint produced the actual Integrity: FAILED status with exit 1.

**What remains open:** A local source checkpoint does not buy credits, resume an unavailable model or back up models, bags, engines and the whole machine.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Intentional corruption of an isolated checkpoint produces Integrity: FAILED. | The helper detects corrupted checkpoint content; all 12 isolated regression tests pass. |

**Evidence files:** `tools/recovery.py`, `tests/test_recovery.py`, `recovery/RESUME.md`, `.recovery/verification/thesis-evidence-2026-11-09/migration/recovery-tests.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J06-integrity-failure-control.log`.


## J07. Checkpoint directory replaced by a file

**What happened:** A tracked directory replaced by a regular file made looking up its former child raise NotADirectoryError.

**Why:** A deleted child path may have a parent that is now a file. Snapshot collection must record that child as deleted while saving the replacement.

**Small steps:**

1. Use a temporary repository with a tracked directory and child file.
2. Replace the directory with a regular file.
3. Catch NotADirectoryError alongside FileNotFoundError during path inspection.
4. Verify the old child is marked deleted and the replacement content is saved.

**Check:** The isolated fixture recorded component/old.cpp as deleted and saved the replacement component file. Its dedicated regression and the complete 12-test recovery suite passed.

**What remains open:** This tests the corrected current behavior; it is not a rerun of the historical buggy implementation.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| A temporary tracked directory is replaced with a regular file. | Current checkpoint records the child as deleted and saves the replacement. |

**Evidence files:** `tools/recovery.py`, `tests/test_recovery.py`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J07-directory-to-file-control.log`.


## J08. GPU query failed inside the sandbox

**What happened:** An early nvidia-smi query failed inside the restricted execution environment.

**Why:** The sandbox did not expose NVIDIA device nodes. A host-accessible read-only query showed the laptop GPU and working driver; the early query did not justify reinstalling the driver.

**Small steps:**

1. Check whether the execution environment exposes the GPU devices.
2. Compare with an authorized host-side read-only GPU query.
3. Record which environment produced each result.
4. Continue GPU tests in the environment with actual device access.

**Check:** The saved environment inventory records RTX 4060 Laptop, 8,188 MiB and driver 595.71.05 outside the sandbox. No new GPU isolation failure was induced.

**What remains open:** This is distinct from the later physical-host driver mismatch. The historical inventory alone is not current hardware health.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| Historical sandbox query could not see NVIDIA device nodes. | Saved host-accessible inventory records the working RTX 4060 and driver. |

**Evidence files:** `config/environment_inventory.json`, `docs/PROJECT_HISTORY_AND_DECISION_RECORD.md`, `recovery/PROGRESS.md`.


## J09. Physical-host kernel and NVIDIA driver mismatch

**What happened:** On the separate alfonso-h017 host, NVIDIA modules did not match the running kernel.

**Why:** User-supplied physical-host logs reported a real kernel/driver mismatch, unlike the laptop sandbox access issue. Matching branch-595 open modules and driver plus reboot reportedly restored access.

**Small steps:**

1. Inspect the actual GPU, running kernel and installed module packages.
2. Simulate the package transaction and check mixed Ubuntu/CUDA sources.
3. Install only the compatible kernel-module/driver set identified for that host.
4. Reboot, then verify GPU access before starting ROS.

**Check:** The physical-host repair record reports restored GPU access. This documentation task did not reinstall drivers or reproduce the fault.

**What remains open:** Later live inference and accuracy on that RTX A4500 Embedded host remain unverified by the supplied logs. These steps are historical, not a universal driver prescription.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| Separate physical host: installed NVIDIA modules did not match its kernel. | Supplied-log summary reports compatible modules/driver and reboot restored access. |

**Evidence files:** `docs/LIVE_OUSTER_TROUBLESHOOTING.md`.


## J10. Ouster Fast CDR serialization symbol failure

**What happened:** The Ouster drivers reported an undefined Fast CDR serialization symbol on the physical host.

**Why:** The driver and ROS/DDS serialization packages were incompatible. The supplied logs reported that updating the compatible package group restored launch.

**Small steps:**

1. Stop the affected ROS nodes.
2. Inspect versions of ouster-ros, ouster-sensor-msgs, fastcdr, fastrtps and typesupport/RMW packages.
3. Update a compatible group after reviewing package resolution.
4. Start the driver and check its actual topic schema.

**Check:** The physical-host record reports launch recovery and an observed 128x1024 cloud with signal and reflectivity but no intensity. No serialization library fault was deliberately created.

**What remains open:** Updating one arbitrary library is not a reproducible general fix. Successful driver launch is not successful model inference.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| Separate physical host: Ouster driver reports an undefined serialization symbol. | Supplied-log summary reports compatible Ouster/ROS/DDS packages restored launch. |

**Evidence files:** `docs/LIVE_OUSTER_TROUBLESHOOTING.md`.


## J11. Model and plugin compatibility uncertainty

**What happened:** A pretrained ONNX was available, but compatible TensorRT libraries and required plugin creators were not established.

**Why:** A trained model still needs an inference runtime and plugins. TensorRT 10.16.1.11 was verified with the exact model; the proposed TensorRT 11 package was not treated as a drop-in replacement.

**Small steps:**

1. Hash and inventory the ONNX and any separate trainable artifact.
2. Inspect input/output tensor metadata.
3. Check VoxelGeneratorPlugin, PillarScatterPlugin and DecodeBbox3DPlugin creators.
4. Parse the exact ONNX and build a target-GPU engine.
5. Run a synthetic smoke test after actual linking.

**Check:** The historical runtime inventory and smoke log record all three creators, successful engine creation and ten synthetic frames. No model, SDK or GPU experiment was rerun for this case.

**What remains open:** Structural and smoke checks do not prove original training parity, object accuracy or TensorRT 11 compatibility.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| An ONNX alone does not establish compatible runtime and plugin availability. | Saved actual SDK smoke reports repeated inference, capacity rejection and empty-result checks. |

**Evidence files:** `config/model_inventory.json`, `config/runtime_inventory.json`, `.recovery/verification/w04-gpu-smoke.txt`, `.recovery/verification/w01-engine-build.txt`.


## J12. System TensorRT installation unavailable

**What happened:** System SDK installation could not proceed through the intended sudo-based route.

**Why:** The actual native workaround extracted the repository DEB and selected component package data into a local SDK, without running maintainer scripts or registering host packages. Docker later used a separate package-install recipe.

**Small steps:**

1. Verify the downloaded repository DEB hash.
2. Extract it into a dedicated local SDK directory.
3. Extract compatible shared libraries, headers and tools; omit unused static archives.
4. Source the local environment helper.
5. Verify the actual plugin registry and linker/runtime before inference.

**Check:** The historical runtime inventory and SDK build/smoke records identify the local extracted SDK and successful native execution. No extraction or host install was repeated.

**What remains open:** Local extraction does not create a complete system package installation. SDK binaries and installers are excluded from source checkpoints.

**Evidence type:** Source-based explanation.

| What was observed | Recorded outcome |
| --- | --- |
| Normal system SDK installation was unavailable through the intended sudo route. | Recorded native method uses a local extracted SDK; Docker later installs its own packages. |

**Evidence files:** `docs/local_runtime.md`, `tools/env_tensorrt.sh`, `config/runtime_inventory.json`, `.recovery/verification/w04-sdk-build.txt`.


## J13. Binding-position and engine assumptions

**What happened:** The old runtime depended on binding positions and assumed an engine interface.

**Why:** A deserialized engine is not automatically compatible. The migrated runtime checks names, roles, types, format, device location, shapes, profile and capacity before binding tensors.

**Small steps:**

1. Require the supported four named I/O tensors and one profile.
2. Check FLOAT32/INT32 types, device locations and linear format.
3. Resolve the batch-one shapes and verify capacities.
4. Set named tensor addresses and execute enqueueV3.
5. Reject an incompatible engine before processing clouds.

**Check:** Current source was inspected; the historical SDK configure/build/smoke logs record actual TensorRT 10 execution. Fresh output-contract tests also passed, but do not instantiate an incompatible GPU engine.

**What remains open:** A full incompatible-engine matrix and exact original-model numerical parity remain incomplete.

**Evidence type:** Source-based explanation.

| What was observed | Recorded outcome |
| --- | --- |
| A positional engine assumption does not validate tensor identity or capacity. | Current runtime checks named roles, types, format and resolved shapes before inference. |

**Evidence files:** `src/pointpillar.cpp`, `include/pp_infer/model_contract.hpp`, `.recovery/verification/w04-sdk-configure.txt`, `.recovery/verification/w04-gpu-smoke.txt`.


## J14. Repeated allocation and stream ownership

**What happened:** Per-frame allocations, resource lifetime ambiguity and unchecked output counts could create stale data or unsafe copies.

**Why:** Owned persistent resources remove repeated allocation. The runtime copies the result count first, checks it against capacity and only then copies box rows; serious GPU-work failure latches the runtime as faulted.

**Small steps:**

1. Create and own the runtime, engine, context, stream and buffers once.
2. Reuse buffers and clear input padding/output count for each cloud.
3. Copy and validate the output count before copying rows.
4. Validate decoded classes, geometry and scores before publication.
5. Drain work during failure unwinding and require restart after a fault.

**Check:** The freshly compiled probe rejected counts -1 and 11 for capacity 10, then accepted count 10. Fresh output-contract tests passed; historical GPU smoke exercised repeated inference and cleanup.

**What remains open:** The current probe validates pure CPU count behavior, not injected GPU faults or complete resource/memory safety.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Counts below zero or above engine capacity are rejected before box-row transfer. | A count equal to capacity is accepted; GPU fault handling remains a separate limit. |

**Evidence files:** `src/pointpillar.cpp`, `include/pp_infer/cuda_resources.hpp`, `include/pp_infer/output_contract.hpp`, `tests/runtime/test_output_contract.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/cpu-output-contract.log`.


## J15. Real SDK version-macro and profiler incompatibilities

**What happened:** Actual TensorRT headers used macro aliases, and TensorRT 10.16 rejected setting the context profiler to null.

**Why:** Parsing a literal version from a header was insufficient. The build now asks the preprocessor; the runtime keeps an owned profiler attached and gates its accumulation.

**Small steps:**

1. Evaluate NV_TENSORRT_MAJOR with a compiler preprocessor guard.
2. Reject unsupported major versions before building the runtime.
3. Keep the profiler alive for the context lifetime.
4. Toggle accumulation instead of passing null.
5. Run actual SDK smoke checks; record callback overhead as unresolved.

**Check:** A compiler-only control using macro aliases rejected major 8 with TensorRT 10 required and accepted major 10. The historical record explains the null-profiler failure and subsequent GPU smoke success.

**What remains open:** The null-profiler GPU failure was not rerun. Callback overhead is not proven absent when timing accumulation is disabled.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Synthetic major-8 header is rejected by the same preprocessor guard used in CMake. | Macro-aliased major 10 passes; historical null-profiler fix retains an owned profiler. |

**Evidence files:** `CMakeLists.txt`, `src/pointpillar.cpp`, `recovery/PROGRESS.md`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J15-version-8-control.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J15-version-10-control.log`, `.recovery/verification/w04-gpu-smoke.txt`.


## J16. Build, ROS logging and shell setup blockers

**What happened:** ROS builds needed C/MPI target support, writable logging and compatible shell setup; an unsourced probe could not load librclcpp.so.

**Why:** Different blockers occurred at different layers. Enable C only for ROS/PCL targets, give tests a writable ROS_LOG_DIR and relax nounset only while sourcing generated setup scripts. Native executables also need the ROS library environment.

**Small steps:**

1. Keep the standalone CPU build independent of ROS/PCL.
2. Enable C in the ROS build path to satisfy exported MPI targets.
3. Use a build-local writable ROS log directory.
4. Source ROS and the overlay with scoped nounset relaxation.
5. Rerun the same executable and compare the actual failure and success.

**Check:** On 9 November the isolated compiled probe really exited 127 with missing librclcpp.so before ROS setup. The same executable succeeded after sourcing Jazzy. The fresh CPU configure and existing ROS data tests also passed.

**What remains open:** The newly observed loader failure is a controlled environment mistake, not a claimed replay of the original MPI/logging failure. No system package change was made.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| New isolated executable really fails to load librclcpp.so without ROS setup. | Sourcing Jazzy allows the same executable to run all current validator controls. |

**Evidence files:** `CMakeLists.txt`, `docker/entrypoint.sh`, `.recovery/verification/thesis-evidence-2026-11-09/migration/J16-unsourced-probe-failure.log`, `.recovery/verification/thesis-evidence-2026-11-09/migration/production-validator-probe.log`, `.recovery/verification/w04-sdk-configure.txt`.


## J17. Sanitizer coverage limitations

**What happened:** Some sanitizer runs could not support the requested coverage; ROS node creation exposed an allocator type mismatch and early GPU instrumentation failed.

**Why:** A sanitizer result has a limited scope. The record separates passing CPU/data checks, distribution ROS allocator behavior, unavailable leak checking and incomplete GPU memory acceptance.

**Small steps:**

1. Run focused CPU address/undefined-behavior checks in a separate build.
2. Record why LeakSanitizer is disabled in the traced environment.
3. Keep the original ROS allocator mismatch log.
4. Test parameter construction normally and instrument data paths separately.
5. Distinguish the failed early GPU instrumentation from the later two zero-error allocation probes.

**Check:** The original saved log contains AddressSanitizer new-delete-type-mismatch through rcutils_string_map_fini. The early Compute Sanitizer log says the application terminated before its first instrumented call. Later reference records report two zero-error allocation checks. No harmful allocator/sanitizer environment was recreated.

**What remains open:** Two allocation probes do not clear internal pooled tensor bounds, races or full GPU failure acceptance. The original allocator error was not hidden with blanket suppression.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| Saved ASan trace reports new-delete-type-mismatch in the installed ROS allocator. | Focused data checks and normal parameter checks are separated; full sanitizer acceptance remains open. |

**Evidence files:** `.recovery/verification/w03-system-allocator-asan.txt`, `.recovery/verification/w03-sanitized-data.txt`, `.recovery/verification/w05-gpu-memcheck.txt`, `docs/MODEL_REFERENCE_COMPARISON.md`, `CMakeLists.txt`.


## J18. Dependency resolution and disk-full builds

**What happened:** Docker package resolution mixed CUDA variants, and bulky build inputs exhausted storage in earlier attempts.

**Why:** Pinning only top-level TensorRT packages let dependencies select another CUDA variant. Shared-library/header-only component selection reduced unused static/development content. Disk space for Docker is separate from the source drive.

**Small steps:**

1. Inspect the resolver error and exact conflicting package variants.
2. Pin the compatible lean, dispatch and plugin dependencies too.
3. Install only required CUDA components and shared/header packages.
4. Check the actual Docker storage filesystem before rebuilding.
5. Remove only identified disposable task-owned cache, then rerun the build.

**Check:** The preserved automatic-deploy-first-failure log genuinely reports cuda12.9 dependencies with cuda13.2 candidates and exit 100. The current Dockerfile explicitly pins the compatible group; later saved full builds passed. Disk-full history is documented, not deliberately reproduced.

**What remains open:** No fresh package installation or disk-full fault was induced. Base tags and all apt dependencies are not a fully hermetic supply chain.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| Saved Docker resolver error mixes required cuda12.9 with selected cuda13.2 dependencies. | Current Dockerfile pins the compatible group; later recorded full builds pass. |

**Evidence files:** `Dockerfile`, `.recovery/verification/automatic-deploy-first-failure.txt`, `.recovery/verification/automatic-dockerfile-only-build.txt`, `docs/PROJECT_HISTORY_AND_DECISION_RECORD.md`, `config/docker_inventory.json`.


## J19. Build an engine for the selected GPU, then reuse it

**What happened:** A saved engine could be missing, built for another GPU, or left incomplete after an interrupted build.

**Why:** A TensorRT engine is tied to its deployment conditions. The image contains the trained ONNX; startup builds a matching execution plan and keeps it in persistent storage.

**Small steps:**

1. Check the selected GPU and retain the ONNX checksum.
2. Calculate the cache identity from model, GPU, driver/CUDA and build settings.
3. Acquire the engine-file lock before checking or building that entry.
4. Build into a pending file, and promote it only after trtexec succeeds.
5. On interruption, stop the builder and remove its pending file.
6. Reuse the matching completed engine on the next startup.

**Check:** Historical startup/restart logs record one engine generation across two successful starts. The present audit rereads the cache and cleanup implementation; it does not rebuild an engine.

**What remains open:** A nonempty corrupted engine is not automatically regenerated. Cross-GPU portability and exhaustive interruption/failure paths remain unaccepted.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| A matching engine was absent at the first recorded startup. | The engine was generated once and reused after restart. Interrupted pending files are removed; corrupted completed-cache recovery remains open. |

**How this part works:**

```mermaid
flowchart TD
    A["Verify model and selected GPU"] --> B["Calculate engine cache identity"]
    B --> C["Acquire cache-entry lock"]
    C --> D{"Matching completed engine exists?"}
    D -->|Yes| E["Reuse engine"]
    D -->|No| F["Build into a temporary pending file"]
    F --> G{"Build succeeds?"}
    G -->|Yes| H["Promote pending file to completed engine"]
    H --> E
    G -->|No or interrupted| I["Remove pending file and report failure"]
    E --> J["Load once and reuse for clouds"]
```

**Evidence files:** `config/docker_inventory.json`, `docker/entrypoint.sh`, `recovery/PROGRESS.md`.


## J20. Stop rebuilding unchanged application inputs

**What happened:** The user saw repeated dependency downloads after edits, and local edits could be absent from a remote-source image.

**Why:** Image preparation, dependency layers and target-GPU engine generation use different caches. Local runtime source is now the default; a matching runtime-input hash skips Docker build.

**Small steps:**

1. Check host GPU access and Docker before attempting the build.
2. Hash only the declared runtime source, build settings and configuration.
3. Compare the hash with the label on the saved image.
4. Skip the build when the hashes match; documentation edits do not change it.
5. When source changes, reuse independent dependency/model layers.
6. Refresh base images only when PP_PULL_BASE=1 is requested.

**Check:** Fresh isolated launcher tests passed reuse after documentation edits, rebuild after runtime edits, explicit pulls/remote source and custom-build-option cache separation. Docker and nvidia-smi are mocks in this rerun.

**What remains open:** First builds, removed caches or changed dependency recipes still require downloads. This fixture is not a new clean-machine Docker build.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| The first fixture invocation requests an image build. | Unchanged inputs and a documentation-only edit skip the build; the recorded Docker calls show no rebuild. |

**Evidence files:** `tools/deploy.sh`, `Dockerfile`, `tests/test_deploy_launcher.py`, `config/launcher_fix_validation.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/deploy_launcher.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-01.json`.


## J21. Make one Ctrl+C stop the owned pipeline

**What happened:** Several Ctrl+C presses were needed, and stopping by container name could target a later unrelated container.

**Why:** The launcher waits interruptibly, records its exact created container ID in a private directory and stops that ID. The Ouster supervisor owns both child process groups.

**Small steps:**

1. Create a private temporary directory for Docker to write the new container ID.
2. Start Docker without automatic signal forwarding and wait with Bash.
3. On Ctrl+C, read and validate the owned ID.
4. Ask Docker to stop that ID with an eight-second cleanup bound.
5. Stop both adapter/detector process groups when either exits.
6. Remove the temporary ID file while retaining the image and good engine cache.

**Check:** The fresh single-SIGINT fixture passed with a fake Docker client that deliberately ignores SIGINT. Fresh supervisor tests also passed peer failure, descendant cleanup and unexpected clean exit. Historical actual GPU launch shutdown took under 0.5 s per launcher.

**What remains open:** The fresh rerun uses isolated processes and mocked Docker; it is not proof for every hung host or application.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| A private fake Docker run client deliberately ignores SIGINT. | One injected SIGINT returns 130 and requests stop for the exact owned ID. Its private CID directory is removed. |

**How this part works:**

```mermaid
flowchart TD
    A["Launcher starts owned container"] --> B["Store exact container ID in private directory"]
    B --> C["Wait for foreground execution"]
    C --> D{"Ctrl+C received?"}
    D -->|Yes| E["Validate the owned container ID"]
    E --> F["Stop that container with bounded cleanup"]
    F --> G["Remove temporary ID directory"]
    G --> H["Return interrupted exit status"]
    D -->|No| I["Continue waiting or handle process exit"]
```

**Evidence files:** `tools/docker_foreground.sh`, `docker/ouster_stack.sh`, `tests/test_docker_foreground.py`, `tests/test_start_ouster.py`, `config/launcher_fix_validation.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/docker_foreground.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/start_ouster.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-05.json`.


## J22. Recognize a running detector that has no input

**What happened:** The terminal became quiet after GPU information and appeared stalled.

**Why:** A cached engine and initialized node can wait normally until a driver or player publishes. Package/executable names and the ROS node name describe different things.

**Small steps:**

1. Inspect the detector log and ROS node information.
2. Confirm that the expected point-cloud topic has an active publisher.
3. Start exactly one intended driver or bag player.
4. Check adapter reception and detector processed/error counters.
5. Open RViz separately using the matching source settings.

**Check:** Historical synthetic and real-bag checks established a running node and later message round trips. Fresh monitor fixtures passed the distinction between a stopped container, a timed-out read and actual counter output.

**What remains open:** A quiet terminal alone cannot diagnose a stall; the fresh fixture does not start a real sensor or detector.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| A stopped container and an unanswered monitor read provide no usable count. | The helper reports refusal or bounded timeout. A separate successful fixture reply is read; it is not scene data. |

**Evidence files:** `docs/STARTUP_AND_REPLAY.md`, `tools/monitor_detections.sh`, `tests/test_monitor_helper.py`, `recovery/PROGRESS.md`, `.recovery/verification/thesis-evidence-2026-11-09/operations/monitor_helper.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-02.json`.


## J23. Match delivery policy as well as topic names

**What happened:** A host viewer received no clouds although container playback was active; best-effort sensor data also conflicted with reliable detector input.

**Why:** The recorded host/container shared-memory path did not deliver in that setup. UDPv4 restored delivery. A best-effort-only publisher generally cannot satisfy a reliable subscriber under DDS.

**Small steps:**

1. Inspect the publisher and subscriber QoS and their actual topic names.
2. For the recorded Fast DDS host/viewer setup, use the tested UDPv4 transport fallback.
3. Receive raw Ouster data with sensor-data best-effort QoS in the adapter.
4. Republish adapted XYZI reliably for the existing detector.
5. Verify received messages and increasing processing counters, rather than discovery alone.

**Check:** Historical observer checks matched 25 frames inside the container and 25 through the host after UDPv4 selection. The actual adapter source declares the two QoS policies. No fresh physical SHM fault was recreated.

**What remains open:** Transport behavior depends on the host/RMW setup. Detector-wide configurable sensor QoS and sustained overload delivery remain open.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| The recorded default host transport received no clouds within eight seconds. | UDPv4 restored host delivery; 25 input/output frames matched. The adapter separately bridges best-effort input to reliable output. |

**Evidence files:** `config/visualization_inventory.json`, `src/ouster_adapter_node.cpp`, `src/pp_inference_node.cpp`, `tools/visualize.sh`.


## J24. Keep the bag and live Ouster profiles separate

**What happened:** The live stack listened on a different raw topic, domain and middleware from the original-bag player; Zenoh had no reachable router.

**Why:** The mismatch combined /ouster1/points + domain 0 + Zenoh with /sensing/lidar/points + domain 99 + Fast DDS. Waiting longer could not align these settings.

**Small steps:**

1. Choose live mode only for a working driver using matching settings.
2. For the original MOSEP recording, start tools/start_ouster.sh bag.
3. Start tools/start_ouster_bag.sh in another terminal.
4. Keep topic, ROS_DOMAIN_ID and RMW_IMPLEMENTATION identical across participants.
5. Pass custom settings through sudo env when sudo would discard exports.

**Check:** Fresh isolated launcher/player tests passed shared Fast DDS/domain99/raw-topic defaults, custom routing and preservation of existing containers. Historical actual GPU replay also confirmed the corrected profile.

**What remains open:** The scripts do not start or repair a live driver or Zenoh router. Fixture success is separate from a current network test.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Live-mode invocation requests Zenoh, domain 0 and /ouster1/points. | Bag mode requests Fast DDS, domain 99 and /sensing/lidar/points, matching the player profile. This captures settings, not fresh discovery. |

**How this part works:**

```mermaid
flowchart TD
    A["Choose source profile"] --> B{"Original MOSEP bag?"}
    B -->|Yes| C["Adapter and player use Fast DDS, domain 99"]
    C --> D["Both use raw topic /sensing/lidar/points"]
    B -->|No: live driver| E["Read actual driver topic, domain and middleware"]
    E --> F["Configure adapter and viewer to match"]
    D --> G["Verify received clouds and increasing counters"]
    F --> G
```

**Evidence files:** `tools/ouster_profile.sh`, `tools/start_ouster.sh`, `tools/start_ouster_bag.sh`, `tests/test_start_ouster.py`, `tests/test_start_ouster_bag.py`, `config/launcher_fix_validation.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/start_ouster.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/start_ouster_bag.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-03.json`.


## J25. Treat the MCAP metadata warning according to observed playback

**What happened:** The player warned that rosbag2 metadata lacked serialized_metadata.

**Why:** The warning appeared while reading the publisher’s original MCAP, but actual playback still published clouds. It was not the established cause of the mismatched-topic failure.

**Small steps:**

1. Keep the original MCAP and metadata.yaml unchanged.
2. Read the player log to identify the exact warning.
3. Check whether raw clouds are actually arriving.
4. Check adapted-cloud and detector counters independently.
5. Record the warning alongside successful observations instead of suppressing or rewriting it.

**Check:** The original player log preserves the warning. The fresh visual observer matched 40 raw/adapted pairs and 39 detection headers; a later snapshot showed processing without input/inference errors. This audit does not rerun the player.

**What remains open:** That observed warning was nonfatal in the recorded replay; other playback errors still require separate diagnosis.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| The original player log reports missing serialized_metadata. | Independent historical observers still verify conversion and detector processing. The original bag is preserved. |

**Evidence files:** `.recovery/ouster-fresh-test/player.log`, `config/ouster_fresh_visual_validation.json`, `docs/FRESH_OUSTER_VISUAL_TEST.md`, `.recovery/verification/thesis-evidence-2026-11-09/operations/mcap-warning-excerpt.log`.


## J26. Open RViz with the right plugin, frame and paths

**What happened:** The Detection3DArray display plugin was missing, sensor-only bags had a TF warning, and moved paths broke generated configuration.

**Why:** The viewer needs its own desktop dependencies. Matching the real sensor frame is sufficient for shared points/boxes; inventing a world transform would hide missing information.

**Small steps:**

1. Install host ROS Jazzy/RViz or use the already prepared desktop.
2. Provide the official vision_msgs RViz plugin, through the system package or verified local extraction.
3. Run the viewer as the desktop user with matching domain/middleware.
4. Choose the actual cloud frame: velodyne for the recorded KITTI demo or lidar/os_lidar for MOSEP.
5. Quote paths containing spaces and regenerate native caches after relocation.
6. Use File → Open Config to update an existing RViz window.

**Check:** Historical actual rendering and isolated plugin bootstrap were verified, including a checkout path with spaces. Genuine RViz captures remain saved. No package installation or current desktop launch was performed for this rerun.

**What remains open:** A sensor-only bag may still lack a world TF tree. Rendering does not establish detection accuracy or complete multi-host portability.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| The recorded desktop lacked the required detection-display plugin and had sensor-only frame information. | The official plugin and actual sensor frame enabled the saved RViz view. No world transform was invented. |

![J26: original capture or live demonstration](figures/thesis/original-first-rviz.png)

Original 2 October RViz capture after display/plugin and transport checks. KITTI data: Geiger et al., KIT/TTI-C, CC-BY-NC-SA-3.0. This is rendering evidence, not accuracy.

**Evidence files:** `tools/visualize.sh`, `config/visualization_inventory.json`, `docs/STARTUP_AND_REPLAY.md`, `.recovery/verification/rviz-current.png`, `.recovery/ouster-fresh-test/rviz-detections.png`.


## J27. Download only needed camera/data assets and resume safely

**What happened:** The first bag had no camera images, while original camera archives were large and downloads could be interrupted.

**Why:** Pinned source identities and checked HTTP ranges let the helper retrieve selected files. Complete checked assets are reused; corrupt completed files are preserved and reported.

**Small steps:**

1. Identify the original recording that produced the bag.
2. Pin the bag checksum and the remote archive object identity.
3. Fetch selected ZIP members with validated range responses and CRC checks.
4. Resume incomplete downloads and promote only verified pending files.
5. Encode and probe the camera video using the separate tool image.
6. Reuse verified completed assets instead of downloading them again.

**Check:** Fresh existing HTTP/range/resume/corruption/timestamp fixture tests passed. Historical actual downloads, MP4 encoding/full decoding and isolated playback remain separate evidence.

**What remains open:** These fixture tests use localhost data, not a new public dataset download. The camera video is unannotated scene context.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| A localhost fixture server ignores the requested byte range; the real helper refuses its response. | A compliant fixture returns only selected archive ranges, and the real helper extracts the correct member with less than one quarter of archive bytes transferred. |

**Evidence files:** `tools/prepare_kitti_demo.py`, `tools/rosbag_demo.sh`, `tests/test_kitti_demo.py`, `config/demo_inventory.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/kitti_demo.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-08.json`.


## J28. Keep camera playback separate from acquisition-time calibration

**What happened:** Camera and LiDAR streams had different counts, offsets or header clocks, so synchronized-looking playback could be misleading.

**Why:** Bag arrival order is not proof of synchronized acquisition. A 30 fps video can hold the same approximately 2 Hz camera image rather than contain new measurements.

**Small steps:**

1. Keep original message headers and bag-record timestamps.
2. Measure the first-frame offset and count the original observations.
3. Build the preview timeline by holding each original image for its recorded duration.
4. Preserve camera payloads and tie ordering in merged playback.
5. Display camera context separately unless extrinsic/time calibration is verified.
6. State that independent video/player speeds are not automatically synchronized.

**Check:** Fresh camera-timeline fixtures passed initial offsets, intervals, final hold, rejection of invalid timelines and preservation of SQLite payloads/timestamp ties. Historical records preserve 111 Ouster images/CameraInfo messages; KITTI offsets are reported separately.

**What remains open:** No calibrated detection-image overlay or acquisition-clock synchronization was established. Preview frame rate is not sensor measurement rate.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| A synthetic image timestamp outside the selected interval is rejected. | Valid synthetic timestamps retain the initial gap, source-image interval and final hold. Playback coordination is not acquisition calibration. |

**Evidence files:** `tools/export_ouster_camera.py`, `tools/prepare_ouster_visual.py`, `tests/test_ouster_camera.py`, `config/ouster_camera_inventory.json`, `config/demo_inventory.json`, `config/kitti_front_inventory.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/ouster_camera.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-06.json`.


## J29. Explain sparse Ouster views without creating points

**What happened:** The Ouster scene looked much sparser than the KITTI view after normalization.

**Why:** The original 32,768-entry scans included 13,206–15,775 zero-range/zero-XYZ returns. Orbit distance, point size and feature coloring also changed appearance; normalization had not moved the retained geometry.

**Small steps:**

1. Count the source entries and invalid zero returns before changing the display.
2. Compare XYZ and other non-intensity bytes between source and adapted streams.
3. Publish a separate original-data topic for visual comparison.
4. Use a closer orbit and larger flat-color points to inspect geometry.
5. Keep zero returns and the original recordings unchanged in this visualization path.

**Check:** The historical detail audit reports five matching live clouds with every non-intensity byte preserved. Source/input counts and display settings are recorded in the detail inventory. No synthetic denser cloud or new inference input was created.

**What remains open:** The raw-view adjustment improves inspection, not scene density or model accuracy. Invalid-return preprocessing remains a separate research change.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| The original Ouster scans include many zero returns; a distant small-point view looks sparse. | The raw-data view preserves geometry and uses a closer, brighter display. No denser scene was synthesized. |

**Evidence files:** `docs/FRONTAL_COMPARISON_AND_RVIZ_DETAIL.md`, `config/ouster_detail_inventory.json`, `rviz/ouster_detail.rviz`, `tools/prepare_ouster_raw_view.py`.


## J30. Bind labels and coordinates to the exact model

**What happened:** Early messages used numeric class IDs with provisional names and intensity scale. A local label file alone did not prove the export order.

**Why:** A model contract needs the exact artifact, its labels, tensor layout and coordinate conventions. Successful deserialization only checks a subset of those assumptions.

**Small steps:**

1. Identify the ONNX by SHA-256 rather than by filename.
2. Compare the repository label file with the recorded exact-version NVIDIA label digest.
3. Read the decoder convention: XYZ is a geometric box center, dimensions follow local axes and yaw is in radians.
4. Keep generic display labels and unresolved training semantics separate from the verified artifact facts.

**Check:** The new read-only check confirms label.txt matches the recorded digest and prints Vehicle/Pedestrian/Cyclist order, axes and remaining contract gaps. No internet lookup or inference is repeated.

**What remains open:** Exact original-training/reference parity, sensor feature equivalence and runtime enforcement of the full semantic contract remain incomplete.

**Evidence type:** Source-based explanation. read-only artifact/contract audit.

| What was observed | Recorded outcome |
| --- | --- |
| Names and scale were provisional. | Exact artifact labels verified; training/input semantics remain partial. |

**Evidence files:** `config/model_contract.json`, `label.txt`, `src/pointcloud_adapter.cpp`, `include/pp_infer/model_contract.hpp`, `.recovery/verification/thesis-evidence-2026-11-09/research/J30.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J30.log`.


## J31. Prove the evaluator responds to correct, missing and duplicate predictions

**What happened:** A plausible score could come from broken matching or ignore logic rather than from the detector.

**Why:** Before interpreting a poor model result, controlled predictions must produce known outcomes. A second identical prediction must not reuse one annotation.

**Small steps:**

1. Create a known annotated box and an identical prediction in an analytic control.
2. Remove that prediction and check that one false negative remains.
3. Add a duplicate and check that only one prediction matches.
4. Run the existing official KITTI metric controls using the already-cached development kit.

**Check:** Actual controls print exact=1 TP/0 FP/0 FN, missing=0/0/1, and duplicate=1/1/0 with precision 0.5. The KITTI controls independently use 41 artificial frames per class and check AP_R40=1 for exact boxes.

**What remains open:** These artificial fixtures verify metric behavior. They are not real-world detector observations or evidence of dataset accuracy.

**Evidence type:** New controlled reproduction. controlled analytic failure reproduction and CPU metric tests.

| What was observed | Recorded outcome |
| --- | --- |
| Missing prediction: 0 TP / 0 FP / 1 FN. Duplicate: 1 TP / 1 FP / 0 FN. | Exact control: 1 TP / 0 FP / 0 FN. Official KITTI controls also pass. |

**Evidence files:** `tests/test_kitti_evaluation.py`, `tests/test_ouster_gt_evaluation.py`, `tools/kitti_evaluation.py`, `tools/ouster_gt_evaluation.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J31.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J31.log`.


## J32. Put predictions and labels in one coordinate and evaluation frame

**What happened:** KITTI labels use camera bottom centers; ROS detections use LiDAR geometric centers. Full scans also contain predictions outside the camera-labeled view.

**Why:** Comparing raw coordinates or counting every rear-facing prediction as a false positive would produce misleading metrics. Calibration, split and visibility rules must be fixed first.

**Small steps:**

1. Load the matching calibration, rectification and camera dimensions.
2. Convert the annotated bottom center to a geometric center and apply the complete transform.
3. Check known centers, dimensions, headings and near-plane image clipping with the existing fixtures.
4. Keep source recording drives separated between the KITTI tuning and test samples.
5. Apply the declared camera visibility and ignore policy before scoring.

**Check:** New tests exercise known camera coordinates, nontrivial translated/rectified calibration, outside-camera exclusion and near-plane clipping. The preserved baseline has 2,876 predictions: 862 camera-visible and 2,014 excluded; frozen drive overlap is zero.

**What remains open:** KITTI camera-upright prediction formatting approximates calibration tilt. Small scenario-selected data and unknown pretrained overlap prevent a population or official leaderboard claim.

**Evidence type:** New controlled reproduction. controlled coordinate/visibility tests plus frozen-policy audit.

| What was observed | Recorded outcome |
| --- | --- |
| Camera bottom centers and full LiDAR outputs are not directly comparable. | Calibration/visibility fixtures pass. Historical baseline: 862 visible / 2,876 predictions; zero split-drive overlap. |

### J32a. Preparation and evaluation hardening retained the original baseline

Initial preparation manifests remain as .initial-pre-review. Source pin/cache hardening revalidated unchanged frame selection/assets. The original evaluator report remains evaluation.pre-review; later image-dimension hardening reproduced every score/count/visibility decision unchanged.

**Scope of this check:** New read-only equality comparison of original records; no preparation or inference rerun.

1. Read the preserved initial and final selection records.
2. Compare every split metric and per-frame visibility decision.
3. Keep old records and report unchanged findings beside the hardened policy.

| What was observed | Recorded outcome |
| --- | --- |
| Earlier preparation/evaluator records were kept before hardening. | 32 frame visibility decisions and all split metrics are unchanged. Policy identity changed; the poor accuracy result did not. |

**Subcase evidence:** `config/kitti_validation_inventory.json`, `config/kitti_accuracy_inventory.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J32a.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J32a.log`.

**Evidence files:** `tests/test_kitti_validation.py`, `tests/test_kitti_evaluation.py`, `tools/kitti_geometry.py`, `tools/kitti_evaluation.py`, `config/kitti_validation_inventory.json`, `config/kitti_accuracy_inventory.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J32.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J32.log`, `.recovery/verification/kitti-rviz-live.png`.


## J33. Accept the poor KITTI result instead of treating valid messages as accuracy

**What happened:** The pipeline rendered boxes, but the labeled test had zero moderate 3D matches.

**Why:** A footprint can overlap correctly from above while the box is too high to satisfy 3D overlap. Valid message fields do not establish correct object locations.

**Small steps:**

1. Keep the first predictions and their model/input identities frozen.
2. Read the class-specific TP/FP/FN and AP_R40 table under the declared policy.
3. Inspect the calibrated height differences of BEV-matched objects.
4. Compare the limited raw-candidate trtexec probe with the ROS output without claiming full parity.

**Check:** The audit verifies the frozen moderate test has zero 3D TP for every class and prints Car BEV AP_R40=5.7516%, Pedestrian=0%, Cyclist=0.02577%. Twelve matched car footprints have median upward error about 1.529 m. An analytic vertical-overlap fixture also passes.

**What remains open:** The diagnostic sample is small and inspected. The probe shares engine/plugins, rounded output and non-unique matching. The height symptom does not justify a universal z correction.

**Evidence type:** Preserved historical evidence. read-only reanalysis of historical negative accuracy plus analytic geometry control.

| What was observed | Recorded outcome |
| --- | --- |
| Rendered boxes did not establish correct objects. | Moderate 3D matches: 0 for all classes. 12 car BEV pairs: median height error +1.529 m. |

![J33: original capture or live demonstration](figures/thesis/original-kitti-ground-truth-rviz.png)

Original 3 October RViz capture of KITTI tuning frame 000368, with green calibrated annotations and predictions. It illustrates the mismatch; the reported test scores come from other frozen observations. KITTI: Geiger et al., CC-BY-NC-SA-3.0.

**Evidence files:** `config/kitti_accuracy_inventory.json`, `docs/KITTI_ACCURACY_RESULTS.md`, `.recovery/accuracy/kitti-baseline-v1/evaluation/report.json`, `.recovery/accuracy/kitti-baseline-v1/diagnostics/test-pairs.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J33.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J33.log`, `.recovery/verification/kitti-rviz-live.png`.


## J34. Separate NMS behavior from inference differences

**What happened:** Poor accuracy raised the question whether migration or duplicate suppression changed the detections.

**Why:** Feeding identical candidate rows to both NMS implementations isolates filtering. Comparing two independently generated candidate sets asks a different question.

**Small steps:**

1. Freeze the same ONNX, points, engine identities and postprocessing settings.
2. Read the preserved TensorRT 8/10 repeated outputs.
3. Apply unchanged NVIDIA NMS and project NMS to identical rows.
4. Match rows uniquely by class and geometric components rather than array order.
5. Report same-candidate agreement separately from cross-runtime numerical variability.

**Check:** The new hash audit checks the saved all-repeat NMS comparison. All 192 same-candidate observations selected the same boxes. Frozen cross-version final-box matching is about 75.70% (median per-frame final-box match fraction), and exact numerical/training parity flags remain false. Duplicate/angle matching fixtures run again.

**What remains open:** TRT8 is a compatibility reference, not a trusted original-training fixture. Both versions can share plugin/input defects. NMS agreement does not exonerate all migration behavior or establish optimal suppression.

**Evidence type:** Preserved historical evidence. hash-verified historical comparison plus unique-matching controls.

| What was observed | Recorded outcome |
| --- | --- |
| Migration and NMS were suspected causes. | NMS agrees on all 192 identical-candidate observations. Median per-frame cross-runtime final-box agreement: 75.70%; exact parity remains open. |

![J34: original capture or live demonstration](figures/thesis/original-trt-reference-rviz.png)

Original 3 October RViz reference comparison on a tuning frame. Cyan boxes are saved TensorRT8 outputs; appearance is not exact numerical parity. KITTI: Geiger et al., CC-BY-NC-SA-3.0.

### J34a. Interrupted raw collection is not automatically complete evidence

The reference collector verifies indexed files against hashes. Unindexed binary outputs are renamed and moved outside the active raw folder before recollection; a changed indexed file is rejected. The older Ouster feature collector instead preserves and refuses unindexed outputs, requiring a fresh folder. These are intentionally different recovery policies.

**Scope of this check:** Read-only AST/source audit. The actual collector also starts Docker/GPU jobs; no extracted imitation of its quarantine branch was run.

1. Inspect how the real collector reads its frozen raw-file index.
2. Trace the changed-file rejection and unindexed-file quarantine branches.
3. Keep archived partial output outside the active raw folder before a future full collection.

| What was observed | Recorded outcome |
| --- | --- |
| A partial binary file is not automatically completed evidence. | Indexed outputs require matching hashes; unindexed outputs are quarantined. This recovery branch was reviewed, not newly executed. |

**Subcase evidence:** `tools/kitti_reference.py:182`, `tools/compare_ouster_features.py:203`, `.recovery/verification/thesis-evidence-2026-11-09/research/J34a.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J34a.log`.

**Evidence files:** `config/kitti_reference_inventory.json`, `.recovery/accuracy/kitti-reference-v1/all-repeat-nms-comparison.json`, `tests/test_kitti_reference.py`, `docker/reference/nms_driver.cpp`, `.recovery/verification/thesis-evidence-2026-11-09/research/J34.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J34.log`, `.recovery/verification/reference-rviz-live.png`.


## J35. Distinguish total point capacity from internal pillar capacity

**What happened:** A cloud could contain fewer than 204,800 points yet exceed the model’s 10,000 occupied-pillar or 32-point-per-pillar limits.

**Why:** The point adapter checks the input allocation. The voxel encoder has additional internal limits and potentially order-dependent point selection.

**Small steps:**

1. Count occupied XY pillars and per-pillar occupancy on the frozen KITTI clouds.
2. Compare these counts with the encoded export limits.
3. Use the existing small first-pillar/first-point control fixtures to test deterministic selection.
4. Keep two historical tuning-only capacity experiments separate from production preprocessing.

**Check:** The audit recomputes 12 of 32 KITTI scans above 10,000 pillars, maximum 15,180, from the hashed capacity report. Existing controls verify stable original-bit/order selection and half-open boundaries. Historical repeated matching improved to roughly 99.6–100% on two altered tuning frames.

**What remains open:** Capacity control changes which points reach inference. It did not establish an accuracy improvement, reproduce CUDA encounter order or deliver a production fix.

**Evidence type:** New controlled reproduction. frozen capacity-count reanalysis plus deterministic selection controls.

| What was observed | Recorded outcome |
| --- | --- |
| 12 / 32 KITTI scans exceed 10,000 occupied pillars. Maximum: 15,180 pillars. | Deterministic capacity fixtures preserve retained bytes/order. Two historical tuning controls improved repeats; no production fix. |

**Evidence files:** `config/kitti_reference_inventory.json`, `.recovery/accuracy/kitti-reference-v1/voxel-capacity-audit.json`, `.recovery/accuracy/kitti-reference-v1/voxel-controls/report.json`, `tests/test_kitti_reference.py`, `tests/test_ouster_point_policy.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J35.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J35.log`.


## J36. Keep allocation memcheck separate from internal tensor safety

**What happened:** The first GPU memory tool failed before checking; later runs reported zero allocation errors, which could be mistaken for complete memory safety.

**Why:** Compute Sanitizer can check allocation boundaries while TensorRT internal tensors share larger allocations. It also does not establish race freedom or all failure behavior.

**Small steps:**

1. Read the original CUDA 12.0 setup failure log without re-triggering a GPU fault.
2. Hash-check the later original/capped CUDA 12.9 memcheck logs.
3. Record each actual exit code and zero-error summary.
4. Keep the two-input allocation scope and unresolved tensor/race checks beside the result.

**Check:** The new audit reopens the historical failed setup and verifies both later logs against their frozen SHA-256. Original and capped runs exited 0 with ERROR SUMMARY: 0 errors. No GPU or sanitizer was run now.

**What remains open:** Two allocation probes do not certify internal tensor bounds, race freedom, leaks, long-run memory stability or complete GPU safety.

**Evidence type:** Preserved historical evidence. hash-checked historical tool-outcome audit; no GPU reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| CUDA 12.0 could not instrument the process. | Two CUDA 12.9 allocation probes: exit 0, zero errors. Internal tensor bounds and races remain unverified. |

**Evidence files:** `config/runtime_inventory.json`, `config/kitti_reference_inventory.json`, `.recovery/verification/w05-gpu-memcheck.txt`, `.recovery/accuracy/kitti-reference-v1/memcheck-results.json`, `.recovery/accuracy/kitti-reference-v1/memcheck-original.log`, `.recovery/accuracy/kitti-reference-v1/memcheck-capped.log`, `.recovery/verification/thesis-evidence-2026-11-09/research/J36.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J36.log`.


## J37. Show why raw Ouster signal caused numerical failures

**What happened:** Initial Ouster replay produced hundreds of saturated-score boxes and 51 logged invalid-output frame drops.

**Why:** Structural XYZI compatibility did not make the fourth feature training-compatible. Raw Ouster signal reached thousands, whereas the model documentation describes a bounded feature range.

**Small steps:**

1. Verify the cached diagnostic image and read-only engine match the historical identities, with working GPU access.
2. Copy and hash-check the historically invalid scan000000 raw-signal and reflectivity/255 inputs into a new output folder.
3. Confirm XYZ bits, order and the 32,768-point count match between encodings.
4. Execute the existing cached pp-reference runner three times per encoding, preserving every raw GPU output.
5. Feed each result to the actual production decode_boxes implementation and record its exit code/error without removing invalid rows.
6. Keep this six-inference numerical reproduction separate from labeled accuracy and from the older 192-observation feature study.

**Check:** New actual GPU run on 9 November: one frozen original Koide scan with 32,768 identical XYZ points and 2,907 occupied pillars, three executions per encoding. Raw signal produced 2,179 candidates each time; each contained one nonfinite length and the actual production decode_boxes rejected it with exit 1, Invalid output box. Reflectivity/255 produced 176,177,176 candidates, zero invalid rows, accepted by that same decoder with exit 0. The cached image/engine identities match; no new engine build, ROS replay or accuracy test occurred.

**What remains open:** This is one unlabeled Koide scan, three raw executions followed by three reflectivity/255 executions, with no warmups or randomized order. It reproduces the numerical/output-contract failure and a working bounded encoding, not calibrated reflectance, accuracy, live ROS delivery, long-run reliability or a universal channel ranking.

**Evidence type:** New controlled reproduction. actual new GPU numerical failure reproduction and real production C++ decoder validation.

| What was observed | Recorded outcome |
| --- | --- |
| Actual GPU reproduction: raw signal rejected 3 / 3 times. Each output had one nonfinite length: Invalid output box. | Same XYZ, reflectivity / 255: accepted 3 / 3 times. Zero invalid rows; 176 / 177 / 176 raw candidates. Numerical success only; accuracy not measured. |

![J37: original capture or live demonstration](figures/thesis/J37-live-decoder-terminal.png)

Actual new terminal capture: the production CPU decoder rejects a newly generated raw-signal GPU output and accepts the paired reflectivity/255 output. The six new GPU runs are separate from the frozen study.

**Evidence files:** `config/ouster_demo_inventory.json`, `config/ouster_feature_inventory.json`, `.recovery/accuracy/ouster-feature-v1/report.json`, `tools/compare_ouster_features.py`, `tests/test_ouster_features.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J37.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J37.log`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/report.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/provenance.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/gpu-command.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/gpu-command.log`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/summary.log`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/compile-decoder.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/cache-and-cleanup-check.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/gpu-pair/decode_check.cpp`.


## J38. Correct a verifier that confused duplicate headers with missing messages

**What happened:** The first full-bag check reported 289 outputs for 291 expected messages.

**Why:** Headers were not unique in the source. A set of timestamps discarded repeated occurrences and made a complete replay appear incomplete.

**Small steps:**

1. Inspect the preserved failed unique-header report.
2. Compare source message occurrences with unique header counts.
3. Count matching occurrences rather than collapsing equal headers.
4. Preserve all original timestamps and rerun the verification logic.

**Check:** The new audit prints the original 291-expected/289-unique result and corrected 291/291 result with 289 unique headers. The second bag has 265/265 occurrences and 264 unique headers. A three-occurrence/two-header synthetic control demonstrates the counting error.

**What remains open:** The correction validates the measurement method for these runs. It is not a detector repair, an accuracy result or a guarantee that every transport experiment is lossless.

**Evidence type:** New controlled reproduction. historical verifier before/after audit plus duplicate-header analytic control.

| What was observed | Recorded outcome |
| --- | --- |
| Old check: 291 expected, 289 unique headers. | Correct check: 291 / 291 occurrences match. Second bag: 265 / 265; source timestamps unchanged. |

**How this part works:**

```mermaid
flowchart TD
    A["Read original source message occurrences"] --> B{"Can source headers repeat?"}
    B -->|Yes: observed| C["Retain repeated occurrences with their original headers"]
    B -->|No| D["Retain each occurrence once"]
    C --> E["Match output occurrences to source occurrences"]
    D --> E
    E --> F["Compare occurrence totals, then report unique-header totals separately"]
```

**Evidence files:** `config/ouster_feature_inventory.json`, `.recovery/accuracy/ouster-feature-v1/ros-first-sequence-unique-header-check.json`, `.recovery/accuracy/ouster-feature-v1/ros-first-sequence.json`, `.recovery/accuracy/ouster-feature-v1/ros-second-sequence.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J38.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J38.log`.


## J39. Publish accepted boxes and meaningful counts

**What happened:** Cluttered boxes made inspection hard, and a missing frame or cumulative total could be mistaken for zero objects or unique tracked objects.

**Why:** A CPU score gate follows NMS. It publishes only accepted boxes and separate aggregate diagnostics/markers; failed frames report unavailable counts rather than successful zeros.

**Small steps:**

1. Validate candidate boxes before applying the score gate.
2. Keep boxes whose score is at least the live threshold.
3. Publish the accepted array with the original cloud header.
4. Report before-filter, removed and accepted counts together.
5. Report input/inference failures separately and mark their per-frame counts unavailable.
6. Inspect timestamps because retained counters may be old; totals count detection events, not unique objects.

**Check:** Historical five C++/ROS output tests, 60 native plus 60 deployed GPU observations and actual RViz rendering verified output semantics. Fresh monitor fixtures passed retained snapshots, bounded waits and stopped-container handling. No new GPU replay was run.

**What remains open:** The gate cannot correct wrong box geometry or guarantee removal of false positives. There is no tracker.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| No response or a stopped container cannot establish zero detections. | The helper reports unavailable data; a separately controlled reply is read. Historical RViz shows actual accepted/removed event counts. |

**Evidence files:** `src/detection_output.cpp`, `tests/ros/test_detection_output.cpp`, `docs/CONFIDENCE_FILTER_AND_MONITORING.md`, `.recovery/verification/published-deployment/rviz-live.png`, `.recovery/verification/thesis-evidence-2026-11-09/operations/monitor_helper.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-02.json`.


## J40. Record the effective threshold rather than assume one default

**What happened:** The native/YAML default was 0.5 while launchers supplied 0.4, risking inconsistent comparisons.

**Why:** A shell override changes startup behavior. A live parameter query is the reliable source for the running value; frozen baseline export refuses undocumented filtering.

**Small steps:**

1. Read the C++/YAML default and launcher override separately.
2. Query confidence_threshold on the running node when performing a live run.
3. Set the intended value explicitly in the experiment configuration.
4. For baseline export, request 0.0 and validate matching per-frame statistics.
5. Refuse changed/nonfinite thresholds or inconsistent counts during collection.
6. Use a new output directory when experiment identity changes.

**Check:** Fresh baseline-gate fixtures accepted unfiltered/empty frames and rejected changed/nonfinite gates, failures, missing fields and mismatched counts. Fresh helper fixtures also confirmed threshold mode only reads the parameter.

**What remains open:** 0.0 disables the additional publication gate, not the model decode cutoff or NMS. No new threshold-specific accuracy claim is made.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Filtered or nonfinite publication thresholds would contaminate the frozen baseline. | The real validator refuses 0.5 and NaN fixture policies and accepts the declared unfiltered policy 0.0. |

**Evidence files:** `docker/node.yaml`, `tools/start_ouster.sh`, `tools/deploy.sh`, `tools/kitti_inference.py`, `tests/test_detection_monitor.py`, `.recovery/verification/thesis-evidence-2026-11-09/operations/detection_monitor.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/monitor_helper.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-07.json`.


## J41. Convert the actual Ouster field numerically

**What happened:** The physical driver produced XYZ plus integer signal/reflectivity but no FLOAT32 intensity; 565 observed clouds were rejected.

**Why:** A sensor-specific adapter must convert the numeric selected channel into a new FLOAT32 intensity field. Changing metadata alone would reinterpret bytes. The production selector still requires literal signal or reflectivity.

**Small steps:**

1. Inspect the incoming PointCloud2 fields, datatypes, offsets and dimensions.
2. Select an existing signal or reflectivity field and declare its divisor.
3. Validate layout, point/byte bounds and divisor before reading data.
4. Copy header/XYZ and numerically convert the selected field into compact XYZI.
5. Publish reliable adapted output and inspect conversion/rejection counters.
6. For unchanged bags naming signal intensity, keep reflectivity selected until a verified alias is separately implemented.

**Check:** Historical compiled converter/ROS tests and 2,224 offline conversion observations exercised numeric layout/header contracts. The fresh original MOSEP test independently checked conversion. This rerun only executes related Python input-contract fixtures, not the C++ converter.

**What remains open:** Alias support for intensity→signal is not deployed. There is no auto-passthrough, channel choice, sensor fusion, ROI crop or production pillar-capacity policy.

**Evidence type:** Preserved historical evidence.

| What was observed | Recorded outcome |
| --- | --- |
| The original physical cloud lacked compatible FLOAT32 intensity; 565 observed frames were rejected. | The separate adapter converts a declared field numerically. The fresh saved pipeline log records reflectivity conversion; literal intensity-to-signal alias support remains open. |

**How this part works:**

```mermaid
flowchart TD
    A["Inspect actual Ouster field layout"] --> B["Explicitly select signal or reflectivity and divisor"]
    B --> C{"Selected literal field and layout valid?"}
    C -->|No| D["Reject and report conversion problem"]
    C -->|Yes| E["Read the selected numerical value"]
    E --> F["Divide by configured divisor and write FLOAT32 intensity"]
    F --> G["Preserve XYZ and sensor header in compact XYZI"]
    G --> H["Publish reliably for the existing detector"]
```

**Evidence files:** `src/ouster_adapter.cpp`, `src/ouster_adapter_node.cpp`, `tests/ros/test_ouster_adapter.cpp`, `config/ouster_adapter_bag_validation.json`, `docs/LIVE_OUSTER_ADAPTER.md`, `.recovery/verification/thesis-evidence-2026-11-09/operations/ouster_demo.stderr.log`, `.recovery/ouster-fresh-test/pipeline.log`.


## J42. Test a fresh unchanged recording without replacing the saved production image

**What happened:** The saved detector image lacked the new adapter, and the user required an original bag plus visible output.

**Why:** A separate derivative image compiled the adapter against existing ROS libraries, preserving detector/model/standard image. The new MOSEP archive was checksum-verified and replayed read-only.

**Small steps:**

1. Download and verify the publisher archive identity.
2. Preserve original extracted files and record their hashes.
3. Build a separate adapter test image when the saved main image lacks it.
4. Mount the original bag read-only and select the matching transport/topic profile.
5. Compare raw/adapted headers and XYZ bytes against independent conversion.
6. Open actual RViz in the source sensor frame and keep sampled counts separate from later snapshots.

**Check:** The historical observer checked 40 raw/adapted pairs and 39 detection headers; a later loop snapshot counted 103 processed frames and zero input/inference errors. Fresh bag-launcher fixtures passed readonly mounting, unchanged fixture bytes, existing-player refusal and image checks.

**What remains open:** The fresh rerun is mocked launcher verification, not another live GPU/RViz run. The original visual test used reflectivity only and did not establish accuracy.

**Evidence type:** New controlled reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| An image missing the adapter and a private bag missing metadata are refused. | With complete fixture inputs, the launcher requests a read-only bag mount. The genuine historical MOSEP RViz screenshot is separate live evidence. |

![J42: original capture or live demonstration](figures/thesis/original-fresh-ouster-rviz.png)

Original 7 November MOSEP replay capture. The adapted cloud, detection display and counters are visible. This earlier loop snapshot differs from the later 103-frame snapshot; it is not labeled accuracy. Source: Gaisberger and Schlager, MOSEP release19353314.

**Evidence files:** `docs/FRESH_OUSTER_VISUAL_TEST.md`, `config/ouster_fresh_visual_validation.json`, `.recovery/ouster-fresh-test/rviz-detections.png`, `tests/test_start_ouster_bag.py`, `.recovery/verification/thesis-evidence-2026-11-09/operations/start_ouster_bag.stderr.log`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-04.json`, `.recovery/verification/thesis-evidence-2026-11-09/operations/observable-scenario-03.json`.


## J43. Obtain independent two-channel annotations without rewriting originals

**What happened:** The weather bags and camera previews could not decide which channel was closer to ground truth.

**Why:** The comparison required original scans containing both channels plus independent object annotations, source integrity and a selection frozen before predictions.

**Small steps:**

1. Use the pinned Dur360BEV-Extended revision and published checksum list.
2. Select 16 published train and 16 published test frames before inference.
3. Retrieve only the required original point/label members through validated ranges.
4. Verify every selected member against the publisher MD5.
5. Retain label conventions and the annotation/split limitations with the results.

**Check:** The new local audit rehashes all 64 original point/label files for 32 frames against the publisher checksum list and prints the frozen selection and provenance. No downloads, conversions or source writes occur.

**What remains open:** The split is index-disjoint within one collection, not verified drive-disjoint. Labels are model-assisted and human-reviewed according to the original paper; the Extended card does not separately document its procedure.

**Evidence type:** Preserved historical evidence. fresh local checksum verification of historical original subset.

| What was observed | Recorded outcome |
| --- | --- |
| Unlabeled weather recordings cannot rank object accuracy. | 32 selected frames / 64 original files pass publisher MD5 checks again. Index-disjoint split; recording independence unverified. |

### J43a. Initial archive-order mapping and selection were replaced before inference

Source provenance explicitly retains the failed initial tar-order mapping selection. The frozen-selection.json and frozen-selection-final.json files have different selection methods; the latter selected uniform archive-ordinal candidates and was frozen before model outputs. Do not use the earlier selection as the final evaluated frame list.

**Scope of this check:** New read-only comparison of preserved manifests and provenance; no download, remapping or model run.

1. Read both preserved selection methods and frame lists.
2. Compare their membership and the recorded archive-ordinal mapping.
3. Use frozen-selection-final.json to identify the evaluated original files.

| What was observed | Recorded outcome |
| --- | --- |
| An earlier archive-mapping selection was preserved. | The evaluated final selection uses a different frozen method. Both manifests remain available; model predictions did not choose the final list. |

**Subcase evidence:** `.recovery/dur360bevet-study/source-provenance.json`, `.recovery/dur360bevet-study/frozen-selection.json`, `.recovery/dur360bevet-study/frozen-selection-final.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J43a.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J43a.log`.

**Evidence files:** `config/ouster_channel_decision.json`, `.recovery/dur360bevet-study/source-provenance.json`, `.recovery/dur360bevet-study/frozen-selection-final.json`, `.recovery/dur360bevet-study/download-verification.json`, `tools/download_dur360_subset.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J43.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J43.log`.


## J44. Exclude an incomplete ROS A/B attempt rather than interpret lost clouds

**What happened:** The initial large-cloud ROS A/B did not finish reliably across host/container UDP transport.

**Why:** Missing delivery cannot be interpreted as zero objects or model inference failure. The subsequent direct C++ comparison answered the feature question with a narrower transport scope.

**Small steps:**

1. Preserve the incomplete ROS recipe, observations and logs.
2. Check its complete flag and number of measured observations.
3. Exclude that unfinished run from the final feature comparison.
4. Use the unchanged production C++ inference/NMS directly for the completed paired study.

**Check:** The new audit prints the actual incomplete flag and observation/warmup counts from ouster-current-ab-v2, alongside its recorded domain and point policy. It does not launch ROS or repeat the delivery failure.

**What remains open:** The completed direct runner does not certify a live ROS signal/reflectivity A/B path. Existing bag signal aliases and target-sensor delivery still need separate verification.

**Evidence type:** Preserved historical evidence. read-only historical incomplete-run audit.

| What was observed | Recorded outcome |
| --- | --- |
| ROS A/B complete=false; no measured observations in v2. | Incomplete run excluded. Completed direct C++ study has narrower transport scope. |

**Evidence files:** `docs/OUSTER_CHANNEL_DECISION.md`, `.recovery/accuracy/ouster-current-ab-v2/observations.json`, `.recovery/accuracy/ouster-current-ab-v2/recipe.json`, `docker/reference/production_runner.cpp`, `tools/run_ouster_ab.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J44.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J44.log`.


## J45. Declare the Dur360 point-selection adaptation and its control

**What happened:** Original 128-beam labeled scans contain 262,144 points, beyond the 204,800-point engine allocation.

**Why:** Both feature variants need identical geometry selection. Input point capacity and internal pillar capacity remain different constraints.

**Small steps:**

1. Record the original point count before preparation.
2. Apply the encoded model ROI and all-zero-XYZ return removal identically to both channels.
3. Audit retained counts and occupied pillars.
4. Prepare a separate first-10,000-pillar/first-32-point sensitivity control.
5. Keep that control out of the production adapter until separately validated.

**Check:** The new recipe audit reports 65,238–175,559 retained points and 20/32 primary scans above the pillar limit; the bounded control has zero above that limit. Existing first-encountered pillar/32-point controls run again.

**What remains open:** ROI and zero-return adaptation changes the input. The deterministic control does not reproduce CUDA thread order or automatically improve accuracy.

**Evidence type:** Preserved historical evidence. frozen recipe count reanalysis plus analytic capacity controls.

| What was observed | Recorded outcome |
| --- | --- |
| Original labeled scan: 262,144 points; engine capacity: 204,800. | Declared ROI/nonzero selection: 65,238–175,559 points. Pillar excess: 20 / 32 primary, 0 / 32 bounded control. |

**Evidence files:** `config/ouster_channel_decision.json`, `.recovery/accuracy/ouster-production-dur360-v2/recipe.json`, `.recovery/accuracy/ouster-production-dur360-bounded-v1/recipe.json`, `tools/ouster_point_policy.py`, `tests/test_ouster_point_policy.py`, `.recovery/verification/thesis-evidence-2026-11-09/research/J45.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J45.log`.


## J46. Recommend reflectivity without claiming accepted 3D accuracy

**What happened:** Reflectivity detected four test vehicle footprints, but neither channel reached the required 3D overlap.

**Why:** BEV evaluates footprint overlap; a vertical displacement can destroy a qualifying 3D match. The recommendation is a fixed experimental encoding/model decision, not a universal sensor ranking.

**Small steps:**

1. Hash-check the saved primary production GPU observations.
2. Recompute the declared evaluator at confidence 0.4 on the CPU.
3. Report per-run Vehicle BEV precision/recall and qualifying 3D matches.
4. Inspect the four first-repeat height errors and 3D IoUs.
5. Keep the primary precision separate from the bounded-control precision.

**Check:** New CPU reanalysis of all 320 primary labeled observations reproduces four versus zero test Vehicle BEV matches, mean precision 27.81% versus zero and recall 6.67% versus zero. Both have zero qualifying 3D matches; saved height errors are 0.60–1.14 m. The full recomputed report is saved.

**What remains open:** Only 16 test scans and 60 in-ROI vehicles; no test Pedestrian matches and no Cyclist ground truth. Repeats are not independent scenes. Primary 27.81% and control 21.99% precision are distinct.

**Evidence type:** Preserved historical evidence. new CPU evaluation of hash-verified historical production GPU observations.

| What was observed | Recorded outcome |
| --- | --- |
| Signal: 0 qualifying Vehicle BEV matches at confidence 0.4. | Reflectivity: 4 / 60; precision 27.81%, recall 6.67%. Both: 0 qualifying 3D matches; height error +0.60–1.14 m. |

**How this part works:**

```mermaid
flowchart TD
    A["Same test scans and independently supplied labels"] --> B["Evaluate both frozen channel encodings at score 0.4"]
    B --> C["Signal: zero qualifying Vehicle BEV matches"]
    B --> D["Reflectivity: four qualifying Vehicle BEV matches per repeat"]
    C --> E["Check complete 3D overlap separately"]
    D --> E
    E --> F["Both channels: zero qualifying 3D matches"]
    F --> G["Use reflectivity as an experimental baseline; investigate height and input contract"]
```

**Evidence files:** `config/ouster_channel_decision.json`, `.recovery/accuracy/ouster-production-dur360-v2/observations.json`, `tools/ouster_gt_evaluation.py`, `docs/figures/ouster-channel-ground-truth-2026-11-08.png`, `docs/figures/ouster-channel-results-summary.png`, `.recovery/verification/thesis-evidence-2026-11-09/research/J46.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J46.log`, `.recovery/verification/thesis-evidence-2026-11-09/research/J46-ground-truth-recomputed.json`.


## J47. Keep planned scheduling and acceptance separate from delivered code

**What happened:** A design for one pending frame could be mistaken for an implemented low-latency worker.

**Why:** Current inference runs synchronously in the ROS callback with reliable depth 700. No sustained benchmark can be inferred from short GPU timings or a viewer refresh rate.

**Small steps:**

1. Read the actual subscription and callback, not only the design diagram.
2. Compare implemented behavior with W06/W07/W08/W09 ledger states.
3. Separate queue policy, delivery settings, stage timing and full end-to-end age.
4. Leave throughput/accuracy acceptance open until agreed targets and sustained tests exist.

**Check:** The new read-only audit prints the actual depth-700 callback evidence and open task states/targets. It launches no workload and marks no benchmark or CI gate complete.

**What remains open:** The latest-frame worker, configurable detector QoS, sustained latency/memory acceptance, broader failure coverage and CI remain unfinished.

**Evidence type:** Open problem. read-only implementation-versus-plan audit.

| What was observed | Recorded outcome |
| --- | --- |
| Design proposes one active and one pending frame. | Actual callback remains synchronous, reliable depth 700. Worker, sustained metrics and acceptance remain open. |

**Evidence files:** `src/pp_inference_node.cpp`, `IMPLEMENTATION_ARCHITECTURE.md`, `recovery/tasks.json`, `docs/MODEL_VALIDATION_PLAN.md`, `.recovery/verification/thesis-evidence-2026-11-09/research/J47.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J47.log`.


## J48. Separate compiler-environment failures from a valid PDF

**What happened:** Built-in compilation repeatedly failed before a complete current thesis PDF could be produced.

**Why:** Missing TeX bundles, network/DNS problems and font dependencies are compiler-environment evidence, not proof that every source page has been checked.

**Small steps:**

1. Read the preserved built-in compiler diagnostics for the actual source.
2. Identify the requested resource and failure stage.
3. Keep the editable source and original figures intact.
4. Report compilation/page-layout acceptance separately from source/link checks.

**Check:** The new audit reads the actual historical compiler JSON and extracts the compile-failed/DNS/article.cls diagnostic. It does not repair networking, install a TeX distribution or claim a new compile pass. The latest native compiler result is reported separately in the thesis verification record.

**What remains open:** A historical separate rendition is not native compilation of the current source. Final PDF and illustrated layout remain unverified until the current source compiles and is inspected.

**Evidence type:** Preserved historical evidence. read-only historical native-compiler diagnostic audit.

| What was observed | Recorded outcome |
| --- | --- |
| Native compiler cannot fetch article.cls / TeX bundle. | Historical compile-failed diagnostic preserved. No source/layout acceptance inferred from this audit. |

**Evidence files:** `.recovery/verification/thesis-history-2026-11-09/latex-compilation.json`, `docs/THESIS_DRAFT.tex`, `config/documentation_review.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J48.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J48.log`.


## J49. Preserve source and artifact identity without leaking large assets

**What happened:** SDKs, models, bags and generated output could accidentally enter Git, while mutable image tags could obscure the tested runtime.

**Why:** Ignore rules protect source control size, not independent evidence backup. Immutable hashes identify an experiment more reliably than a tag. Authentication advice is not an executed login.

**Small steps:**

1. Run git check-ignore on representative generated/model paths.
2. Keep editable code, reports, figure provenance and small summaries versioned.
3. Identify the model and tested image using frozen hashes.
4. Back up ignored data and logs independently.
5. Keep historical GitHub authentication guidance separate from actual credential actions.

**Check:** The new audit runs the real git check-ignore command and prints frozen model/image identities. It reads or changes no credentials, stages nothing and pushes nothing.

**What remains open:** Ignore rules do not remove already-tracked content or back up ignored evidence. Base tags/non-GPU apt packages are not fully pinned, so source pinning alone is not hermetic reproduction.

**Evidence type:** Source-based explanation. actual ignore-rule check plus frozen identity audit.

| What was observed | Recorded outcome |
| --- | --- |
| Large generated artifacts and mutable tags weaken traceability. | Actual ignore rules verified; immutable model/image identities recorded. Credentials untouched; ignored evidence needs its own backup. |

### J49a. A frozen recipe rejects silent changes

freeze_json compares canonical bytes with an existing record and requires a fresh output directory if they differ. This prevents a new model, selection or policy from quietly replacing a named experiment.

**Scope of this check:** Actual freeze_json exercised only in a temporary directory; expected mismatch raises ValueError, child exits1 and original bytes are preserved.

1. Create a temporary recipe using the actual freeze_json function.
2. Retry identical content and verify it is accepted.
3. Change the model identity and record the actual refusal while checking original bytes.

| What was observed | Recorded outcome |
| --- | --- |
| A frozen recipe already records model A. | Identical retry succeeds. Model B is refused. Original recipe bytes remain unchanged. |

**Subcase evidence:** `tools/prepare_kitti_validation.py:44`, `tools/kitti_evaluation.py:176`, `.recovery/verification/thesis-evidence-2026-11-09/research/J49a.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J49a.log`.

**Evidence files:** `.gitignore`, `.dockerignore`, `config/model_contract.json`, `config/kitti_reference_inventory.json`, `docs/PROJECT_HISTORY_AND_DECISION_RECORD.md`, `.recovery/verification/thesis-evidence-2026-11-09/research/J49.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J49.log`.


## J50. Reject attractive but unsupported quick fixes

**What happened:** Changing a confidence threshold or shifting boxes could make a display cleaner without resolving the model mismatch.

**Why:** A gate can remove a prediction but cannot move it. A label-fitted offset might improve the inspected data while hiding a training/frame or decoder problem.

**Small steps:**

1. Use a known analytic box pair with identical footprints and a one-metre height error.
2. Measure BEV and 3D overlap separately.
3. Raise the confidence gate and verify it changes selection, not geometry.
4. Keep real measured coordinates frozen while investigating the input/training contract.
5. Choose any future correction on development data, then evaluate fresh recording-disjoint data.

**Check:** The new analytic control prints BEV IoU=1 and 3D IoU=1/3 for the elevated box. At the declared 0.7 Vehicle criterion it remains a miss; raising confidence removes the prediction but does not recover the object. Existing vertical and score-boundary tests pass.

**What remains open:** The analytic example explains a mechanism; it is not a fitted correction, a real scene result or authorization to change production z coordinates.

**Evidence type:** New controlled reproduction. controlled analytic geometry/threshold failure reproduction.

| What was observed | Recorded outcome |
| --- | --- |
| Analytic elevated box: BEV IoU 1; 3D IoU 1/3. | Raising confidence removes the box but does not move it. No measured coordinates or production settings changed. |

**Evidence files:** `tests/test_ouster_gt_evaluation.py`, `tools/ouster_gt_evaluation.py`, `docs/OUSTER_CHANNEL_DECISION.md`, `docs/MODEL_VALIDATION_PLAN.md`, `.recovery/verification/thesis-evidence-2026-11-09/research/J50.json`, `.recovery/verification/thesis-evidence-2026-11-09/research/J50.log`.
