# Implementation progress

Updated: 2026-10-01 (Europe/Berlin).

## Scope and decisions

- User requested architecture, implementation steps and a recovery mechanism for model credit exhaustion.
- User confirmed Ubuntu 24.04 / ROS 2 Jazzy on an NVIDIA GPU.
- Proposed runtime: one process, one worker/context/stream, at most one pending frame; CPU correctness independently buildable.
- Source baseline: `2301135`; original `PROJECT_REVIEW_AND_UPDATE_PLAN.md` was already untracked. Preserve user changes.
- C++/ROS modernization was authorized and started 2026-10-01. Task state lives in `tasks.json`; checkpoint manifests record work-in-progress, and actual files/evidence take precedence over stale status labels.

## Current handoff

W00 is verified: architecture, task ledger, recovery runbook and tested local checkpoint helper are delivered. No production inference code was changed. See the latest complete W00 checkpoint for the final source snapshot.

W02 CPU core and W03 local ROS input/config/output adapters are implemented and verified. W01 has progressed with a discovered ONNX export/training artifact and GPU identification, but runtime compatibility remains blocked. Read-only GPU query outside the sandbox now passes. Next: select/provision compatible TensorRT/plugin binaries or source/build versions and create/validate the target engine. Do not claim a GPU gate passed until the model/plugin/hardware contract is established.

## W00 verification evidence

- Command: `python3 -m unittest discover -s tests -p 'test_recovery.py' -v`; exit 0; **12 tests passed**.
- Log: `.recovery/verification/recovery-tests.txt`; SHA-256 `fc094b1484ad6780f1f40d94cfd265e7dbeddae35c5a33b8d7e6b33b6a3b9fee`.
- Coverage: untracked source, tracked edits/deletions, separate index/worktree patches, unchanged source/index/HEAD, symlink boundaries, exclusions/caps, ignored partial checkpoints, corruption, drift, changed HEAD, and a directory replaced by a file.
- Initial real checkpoint `20261001T195647.623355Z-40f4c430` and `python3 tools/recovery.py status` succeeded; SHA-256 integrity OK, unchanged HEAD and no captured-file drift. Only four existing image/media files were excluded.
- Independent architecture and recovery reviews completed. The directory-to-file checkpoint bug found in review was repaired and included in the passing regression suite.
- Ledger IDs/dependency order and local documentation links were checked. `git diff HEAD` for production sources/build/launch files was empty.
- The final checkpoint is created after this handoff update; use `status` to locate it and detect subsequent changes. Its `verified` state applies to W00 only.
- No commands or benchmarks remain running from this task. No installation, branch change, commit or external publication was performed.

## Environment observed

- x86_64, Ubuntu 24.04.4, ROS directory `/opt/ros/jazzy`.
- Python 3.12.3, CMake 3.28.3, colcon installed, nvcc 12.0.140.
- `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader` exited 9: could not communicate with NVIDIA driver.
- No `NvInfer.h` under `/usr/include` (other locations not ruled out).
- No `.engine`, `.plan`, `.onnx` or `.etlt` in checkout.
- Installed Jazzy headers confirm nested `hypothesis.class_id` / `hypothesis.score`.
- No C++ build, inference, sensor test or benchmark performed.

## Requirements still needed for W01/W08

Target TensorRT engine and compatible plugin build provenance; class/normalization/coordinate contract; LiDAR rate and maximum points/bytes; representative bag and reference labels; allowed frame age/miss rate/drop fraction and accuracy tolerance. The GPU/VRAM/driver and exported/training artifacts have now been verified/located (see W01 inventory below).

## Update protocol for implementation sessions

Before each checkpoint append: task/substep, files changed, decisions, exact check command, exit code, evidence/log path, what remains unverified, any active process and the next concrete action. Do not store keys or credentials. Only one writer updates this handoff/ledger at a time. Mark dependent tasks stale when a prerequisite changes after verification.

## W02 implementation evidence

- Added C++17 `pp_core` and CPU-only CMake path; reusable CMake library targets/imported CUDA/TRT discovery replace fixed toolkit/paths/NVCC flags. Runtime remains explicitly gated to legacy TensorRT 8 until W01/W04 migration.
- Removed CPU geometry CUDA dependency; convex polygon clipping replaces unsafe intersection accumulation/division. Tests cover analytical rotated overlap, touching/degenerate cases, finite inputs, stable ties, candidate bounds, output clearing and optional class-aware suppression. Existing four-argument callers retain class-agnostic suppression and the legacy `>=` threshold rule. Model-reference accuracy is still required.
- Removed missing/unused includes and declared dependencies. Production GPU build remains unverified.
- `cmake -S . -B .recovery/build/core -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=OFF -DCMAKE_BUILD_TYPE=Debug -DPP_ENABLE_SANITIZERS=ON`; `cmake --build .recovery/build/core -j2`: exit 0.
- First ctest failed because LeakSanitizer cannot operate under this environment's ptrace. `ASAN_OPTIONS=detect_leaks=0 ctest --test-dir .recovery/build/core -V`: exit 0; 15 cases plus 2000 randomized pairs passed with AddressSanitizer/UndefinedBehaviorSanitizer. Leak checking was not verified. Log: `.recovery/verification/w02-core.txt`; hash recorded in tasks.json.
- No installation, commit or branch change. Next: W03 fixtures using explicit test contracts; actual model contract pending W01.

## W03 implementation evidence

- Added checked capacity arithmetic and `InputLimits`, a PCL-based FLOAT32 XYZI adapter, typed read-only processing configuration, and Jazzy Detection3DArray construction. Wired the helpers into the legacy node. Raw point count/bytes are bounded before PCL allocation; valid empty input skips inference. Input supports little-endian scalar fields and organized row padding; unsupported layouts are rejected explicitly. Nonfinite points are removed. Numeric-string class IDs preserve current consumer semantics.
- Test configuration: `source /opt/ros/jazzy/setup.bash`; `cmake -S . -B .recovery/build/ros -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=ON -DPP_ENABLE_SANITIZERS=OFF -DCMAKE_BUILD_TYPE=Debug -DPython3_EXECUTABLE=/usr/bin/python3`; `cmake --build .recovery/build/ros -j2`; `ctest --test-dir .recovery/build/ros --output-on-failure`: exit 0, three CTest executables/modes covering 15 core + 11 data + 2 parameter cases. Logs: `.recovery/verification/w03-normal.txt`.
- With `PP_ENABLE_SANITIZERS=ON`, CPU core and 11 cloud/message data cases passed using `ASAN_OPTIONS=detect_leaks=0`. Log: `.recovery/verification/w03-sanitized-data.txt`. Parameter-node creation under ASan exposed `new-delete-type-mismatch` in installed `rcutils_string_map_fini` via ROS entity construction; saved failure log `.recovery/verification/w03-system-allocator-asan.txt`. Parameter checks are separate normal-build tests; no blanket sanitizer error suppression was introduced. Leak checking remains unavailable under ptrace.
- ROS tests originally attempted to log outside writable roots; CTest now gives parameter tests a writable build-local ROS_LOG_DIR. Ubuntu's PCL/VTK exports required enabling C only in the ROS build path to supply MPI::MPI_C. Core-only builds still discover only a C++ compiler.
- DDS socket access is restricted in this execution environment. Local message/parameter behavior passed; live topic delivery/QoS integration is unverified. The full CUDA/TensorRT executable cannot be built/validated here yet. Binding dtype/layout, persistent buffers, enqueue/output-count safety and worker ownership remain W04–W06 work.
- README contains runnable CPU/ROS test commands. Git diff whitespace and package dependency declarations checked. Exact test log hashes are in tasks.json.

## W01 model/hardware inventory (partial, runtime gate blocked)

- User supplied `/home/ae/Downloads` as the artifact location.
- `/home/ae/Downloads/pointpillars_deployable.onnx`: 5,572,374 bytes; SHA-256 `2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`.
- `/home/ae/Downloads/pointpillars_trainable.tlt`: 135,219,699 bytes; SHA-256 `4e901182d10f40023bd5924ef8d5b7eca493901fc80029582a4c2abaf33e4f2f`. Hashed only; not deserialized/decrypted or executed.
- `python3 tools/inspect_onnx_metadata.py /home/ae/Downloads/pointpillars_deployable.onnx`: exit 0. Bounded read-only metadata extraction using the official ONNX schema; not ONNX checker/shape inference or a TensorRT smoke test. ONNX/protobuf Python packages are absent; no dependencies were installed.
- IR 8/opset 11. Inputs: `points` FLOAT32 `[batch,204800,4]`, `num_points` INT32 `[batch]`. Outputs: `output_boxes` FLOAT32 `[batch,393216,9]`, `num_boxes` INT32 `[batch]`. Plugin operator names: `VoxelGeneratorPlugin`, `PillarScatterPlugin`, `DecodeBbox3DPlugin`. Batch is symbolic in ONNX; engine profile and actual runtime I/O must still be inspected. Class labels/order and normalization cannot be established from these tensor shapes.
- `lspci -nn -s 01:00.0` identifies NVIDIA AD107M / GeForce RTX 4060 Max-Q / Mobile `[10de:28e0]`.
- Inventories: `config/model_inventory.json`, `config/environment_inventory.json`. They deliberately are not a compatible environment lock or a verified engine contract. Models remain at their original paths outside Git; recovery snapshots capture inventory, not model binaries.
- No engine/plugin libraries found in Downloads outside unrelated IDE directories. W01 remains blocked on a selected/provisioned TensorRT/plugin stack, target engine smoke test and training/export semantics. W04 cannot pass until W01 is resolved; independent mailbox harness work can proceed before full integration if requested/needed.
- No installs, commits, branch changes or external publication. No test/build process remains running after this handoff.

### Corrected GPU access finding

- NVIDIA kernel module and PCI driver binding were present, but `/dev/nvidia*` was absent inside the sandbox. A read-only `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader` outside the sandbox exited 0: **NVIDIA GeForce RTX 4060 Laptop GPU, driver 595.71.05, 8188 MiB VRAM**. The earlier failure reflected execution-environment device access; no host driver repair was performed or justified by that failure.
- Runtime/engine smoke checks will likewise need GPU-accessible execution. GPU inference itself has not been tested. W01/W04 remain blocked on the NVIDIA inference stack/artifact gate, not an established host driver fault.

## W04/W05 TensorRT 10 preparatory migration (2026-10-01)

User explicitly authorized runtime migration while TensorRT 10.16.1 downloads. W01 remains an acceptance gate; this preparatory work does not imply SDK/engine validation.

- Replaced legacy TRT wrapper with a PIMPL runtime using named tensors, resolved batch-one shapes, setTensorAddress and enqueueV3. Requires four exact device/linear FP32/INT32 I/O contracts and a single optimization profile. Capacity/count arithmetic is checked. ONNX building/parser dependency removed from runtime; engines are read in binary and must be created offline.
- Runtime/logger/engine/context/profiler use deterministic ownership. Persistent nonblocking stream and four device buffers replace managed per-frame allocations, abort/exit and device-wide synchronization. Input padding and result count are cleared; transfers/enqueue/completion use the same stream. Output count is bounds-checked before copy. Failed GPU operations poison the runtime until restart and drain outstanding work before unwinding input/stack references. No stale detection vector can escape failure.
- ROS node now owns PointPillar with unique_ptr and passes packed CPU points to the runtime; removed callback CUDA allocations/events/streams and raw runtime ownership. It remains synchronous with legacy queue depth 700; bounded latest-frame worker/QoS/shutdown metrics are W06/W07 and not implemented here.
- Added pure output-contract checks for counts, fractional/negative/out-of-range/nonfinite class IDs, bad geometry/score, and empty data. Class order and coordinate semantics still require the export specification and reference fixture; class-agnostic NMS unchanged.
- Public headers downloaded from https://api.github.com/repos/NVIDIA/TensorRT/contents/include?ref=release/10.16 to /tmp/pp-trt10-headers for compile-only checks. No libraries installed, no SDK linker check, no engine generated. Runtime/node syntax checks exit 0; exact commands/logs and SHA256 are in tasks.json. Temporary headers are not recovery artifacts; re-fetch or use actual SDK if /tmp is cleared.
- CPU ASan/UBSan CTest passed both geometry (15 cases plus 2000 randomized pairs) and output-contract test. Normal ROS build passed all four modes. Leak detection disabled under ptrace as previously documented. These tests do not simulate TensorRT/CUDA failure paths or confirm actual plugin implementations.
- Next: inspect the completed DEB, provision exact SDK/development packages, build/link full node, verify plugins, generate engine and validate target behavior. Full W04 and W05 acceptance remain unfinished.

## Actual TensorRT SDK/engine validation (2026-10-01)

- Completed user download inspected: Ubuntu 24.04 amd64 local repository, package version 1.0-1, SDK components 10.16.1.11-1+cuda12.9. sudo requires password; instead extracted package data into ignored .recovery/sdk/repository and .recovery/sdk/tensorrt-10.16.1. No maintainer scripts executed, no apt/dpkg registration, no driver/system changes. Extracted runtime, development headers, plugins, parser, trtexec/Python and associated lean/dispatch/vc components. Metadata/hash inventory in config/runtime_inventory.json.
- System Python 3.12 loaded SDK 10.16.1.11. Registry contains VoxelGeneratorPlugin, PillarScatterPlugin, DecodeBbox3DPlugin, all version 1 namespace empty. Actual ONNX parser created all three plugins successfully.
- trtexec built batch-one engine with points 1x204800x4 and num_points 1; workspace 1024MiB, noTF32, skipInference. Engine generation ~11 seconds, 8.55MiB. Final artifact .recovery/engines/pointpillars-fp32.smoke.engine; hash in inventory. Smoke suffix deliberately does not imply accuracy validation.
- Full runtime, smoke executable and ROS node built/linked against actual SDK and installed CUDA toolkit 12.0.140. SDK uses macro aliases for major version; CMake now checks with C++ preprocessor. Config/build logs under .recovery/verification/w04-sdk-*.txt.
- First smoke revealed TensorRT setProfiler(nullptr) is rejected. Fixed by retaining persistent owned profiler and gating its accumulation. Clean repeat passed ten frames, capacity rejection and empty-result checks; no TRT API errors. Profiler callbacks remain attached and can affect latency even when collection is disabled. Synthetic smoke is not detection accuracy or a benchmark.
- Four CPU/ROS CTest modes passed in the actual SDK build. Installed Compute Sanitizer failed library lookup initially, then with documented injection path exited 255 before instrumentation; no CUDA memory-validation pass. No compatible sanitizer installation attempted.
- Added tools/env_tensorrt.sh and docs/local_runtime.md with working local SDK/build/smoke commands. SDK/engines/logs are ignored and excluded from recovery snapshots. Keep original DEB/ONNX independently; inventory records their provenance. No model fixture/class/normalization claims invented. W01/W04/W05 acceptance remains incomplete; W06 latest-frame worker not yet implemented.

## Node running (2026-10-02 Europe/Berlin)

User requested build and run. Rebuilt actual SDK runtime and all four CTest modes passed. Started .recovery/build/runtime/pp_infer with .recovery/run/node.yaml; PID 7485 at startup, exec session 74874. Host GPU/DDS access enabled. Registered /minimal_publisher, /point_cloud PointCloud2 subscription and /bbox Detection3DArray publisher. No live cloud publisher existed before startup. Provisional classes class_0/class_1/class_2 and intensity_scale 1.0 are startup settings, not verified training semantics. Existing reliable subscription may not match best-effort LiDAR publishers; W06/W07 remain unfinished.

One synthetic frame was published and a Detection3DArray received with preserved header; evidence .recovery/verification/node-ros-smoke.txt. Running node left active as requested. Logs .recovery/run/node.log; stop with kill -INT 7485 after verifying PID command (PIDs can be reused). Artifacts under .recovery are not backed up by source checkpoints. Real data accuracy and memory instrumentation remain pending.

## Colcon workspace verified (2026-10-02)

User requested colcon build. Default build/install/log directories are ignored. CMake reads TENSORRT_ROOT from the environment and searches multiarch include/library paths. After source /opt/ros/jazzy/setup.bash and tools/env_tensorrt.sh, colcon build --packages-select pp_infer --cmake-args -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3 passed. Source install/setup.bash resolves `ros2 pkg executables pp_infer` to `pp_infer pp_infer`; installed executable shared dependencies resolve with the sourced environments. Colcon test reports 4 tests, 0 errors/failures/skips. Logs .recovery/verification/colcon-*.txt. Existing directly launched node was left unchanged; no duplicate node started.

## Portable Docker packaging delivered (2026-10-02 Europe/Berlin)

User requested a two-command image build/run and portability across different NVIDIA hardware. Added Dockerfile, restrictive .dockerignore, docker/entrypoint.sh, docker/node.yaml, docker/README.md and CUDA-based pp_device_info. No RTX4060 assumption in runtime/device selection. SM>=7.5 follows TensorRT10 support; unsupported CUDA/driver/devices fail preflight. The image is amd64 Linux; ARM/Jetson requires separate platform SDK/images, not a false universal compatibility claim.

- Full multistage image build passed including four colcon tests. Optimized runtime uses Ubuntu24 ROS runtime packages and CUDA shared libraries; compiler/development stack stays in build stage. Final image identity is in config/docker_inventory.json.
- Startup respects CUDA_VISIBLE_DEVICES, allows PP_GPU_INDEX selection, and uses CUDA device0 consistently after mapping. Cache includes GPU UUID/compute capability, driver and CUDA API/runtime versions, ONNX hash and workspace/SDK recipe. Builds ONNX locally on target GPU with noTF32 FP32, batch1; lock serializes shared-cache builds and pending engine is promoted only after trtexec succeeds. PP_WORKSPACE_MIB controls workspace, not total memory.
- Initial container failed ROS setup due nounset; fixed source entrypoint by relaxing nounset only while sourcing ROS/overlay. Applied final entrypoint update to already compiled image to avoid another huge development-image download. Future full Dockerfile copies same corrected source.
- New container built its engine in ~10s and processed a synthetic ROS frame, preserving header. Stop/start repeated synthetic round trip and reused engine; logs contain exactly one generation across two starts. Invalid GPU index failed before engine/ROS startup. Logs/hashes in tasks.json; validation domain87 isolated from host ROS. Test container stopped/removed; pp-infer:jazzy-trt10 image and pp-engines volume retained.
- Disk was exhausted during original development-image work. User removed unused extracted libnvinfer_static.a. Removed only task-owned SDK source-context cache 9tnk7goyebx8yqyz12dydk5fi and obsolete unshared CUDA development cache xl7tkso9tj12rs52jt59og3uj. Original model/DEB, active SDK, final image and unrelated Docker data retained. Temporary original extracted repository was already removed. Do not re-delete referenced cache IDs blindly; inspect current ownership/state. Initial bulky build log is not relied on as final verification evidence.
- The Docker build context still requires prepared ignored SDK/model data; built image carries these and runs elsewhere without host ROS/CUDA toolkit/TensorRT. Driver and NVIDIA container support remain host prerequisites. Dockerfile alone is not a model/SDK backup. Source snapshots omit binaries, Docker layers and volumes. Only RTX4060 physically tested, no reference accuracy or CUDA instrumentation pass. W06/W07 and full CI/benchmark acceptance remain unfinished.

### Final build-footprint correction and revalidation

Final Dockerfile now builds from Ubuntu24 and installs only pinned CUDA packages: cudart-dev 12.9.79, nvcc/NVRTC/nvJitLink 12.9.86 and cuBLAS 12.9.1.4. This avoids downloading the full oversized NVIDIA development image for future builds. Runtime copies only shared CUDA/SDK libraries and installed ROS/node artifacts. Final full source Dockerfile build passed including four colcon tests; supersedes the intermediate entrypoint-only image update.

Final image was tested with a fresh validation cache: engine generation, synthetic ROS/GPU frame with preserved header, then stop/start and second frame. Exactly one engine generation across two starts confirms reuse. The final validation container and its temporary volume were removed; reusable pp-engines volume and finished pp-infer:jazzy-trt10 image retained. Updated immutable image ID and reported size in config/docker_inventory.json. Logs/hashes in tasks.json. These are execution checks on the available RTX4060, not accuracy/multi-hardware/ARM evidence.


## A-to-Z deployment document and README (2026-10-02)

- Added standalone `docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex` with natural-language explanations of completed work, host driver installation, Docker/Container Toolkit setup, exact model/SDK preparation, two-command build/run, node/topic inspection, QoS and bag playback, synthetic check, image/source transfer, optional full native ROS/CUDA/colcon setup, configuration, troubleshooting, and development recovery. Target limits and unfinished milestones are explicit.
- Replaced README's mixed modern/historical procedures with the current Jazzy workflow and links. Preserved old instructions in `docs/LEGACY_FOXY_README.md`; they are marked historical. Docker README now links the full guide and gives the container a consistent name for inspection commands. No runtime source or image changes.
- Verified 33 LaTeX shell blocks using `bash -n`, two embedded Python heredocs using `ast.parse`, nine current README/Docker local links, environment delimiters/escaping, actual ONNX hash, and `git diff --check`. Logs: `.recovery/verification/docs-command-checks.txt`. SDK package path/version format was inspected read-only in the original outer DEB; fresh host installations and full SDK extraction were not repeated.
- Extracted and executed the guide's exact synthetic Python in temporary container `pp-guide-validation`, existing image `pp-infer:jazzy-trt10`, ROS domain 91, normal engine cache. Exit 0: GPU/ROS detections with preserved header, one detection. Confirmed `ros2 bag play` exposes `--remap` and `--qos-profile-overrides-path`. Logs: `docs-container-smoke.txt`, `docs-container-startup.txt`, `docs-bag-help.txt` under `.recovery/verification`. Temporary container stopped/removed; unrelated running container was retained. Not accuracy evidence or another GPU test.
- Open-in-Codex requested the .tex editor (queued for this thread). Built-in compile attempted twice: unavailable TeX bundle could not be retrieved from `relay.fullyjustified.net`; failure occurred before source parsing. PDF compilation/layout remain unverified. Exact diagnostic: `.recovery/verification/docs-latex-compile.json`. Source preserved; no terminal TeX installation or exported PDF.
- W09 remains in progress: clean-machine/hardware rehearsal, full operational/CI acceptance and benchmark dependencies are not complete. Documentation is delivered, with PDF compilation blocked by compiler bundle availability.


## Colcon documentation revision (2026-10-02)

- Revised the open `docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex` in place: all direct CMake/CTest commands now use colcon build/test/test-result, isolated CPU/sanitizer/ROS directories, and the correct default colcon runtime smoke artifact `build/pp_infer/runtime_smoke`. Explained `--cmake-args` and the expected no-install-target warning for the deliberately reduced CPU configurations. CMake remains the package's backend/dependency.
- README CPU commands and `docs/local_runtime.md` use the same workflow. Runtime source, Dockerfile/image, historical evidence and legacy instructions unchanged.
- Executed the documented reduced workflows: CPU build/test/result passed (2 tests); sanitized CPU build/test/result passed (2 tests, ASAN_OPTIONS=detect_leaks=0); ROS adapter build/test/result passed (4 tests). Commands use `.recovery/colcon-doc/{core,core-sanitized,ros}/{build,install}`. Exact build/test/result logs are `.recovery/verification/docs-colcon-*`. No new native GPU validation claimed.
- Checked 34 LaTeX command blocks, embedded Python, Markdown blocks/links, smoke path and whitespace. Built-in compile was called after editing; same uncached TeX bundle download failure occurred before parsing. Current editor kept open; PDF compilation remains unverified. No TeX installation or replacement document.


## Git push preparation: artifact exclusions (2026-10-02)

- Expanded `.gitignore` to exclude downloaded SDK installer packages, model weights/exports, TensorRT engines, sensor recordings, source/container archives, Python caches, and generated LaTeX output. Existing SDK/recovery, colcon outputs, and Docker asset exclusions retained. Editable LaTeX, inventories, source and recovery records remain eligible.
- `git check-ignore -v` confirmed the 5.17 GB root TensorRT DEB, root ONNX/TLT, Docker model, and extracted SDK are ignored. Inspected tracked plus untracked/addable files: none above 10 MiB; no model/SDK binaries staged. No already-tracked large artifact needed removal. `git diff --check` passed. No asset deleted, commit made, or push performed; user can stage reviewed source changes.
