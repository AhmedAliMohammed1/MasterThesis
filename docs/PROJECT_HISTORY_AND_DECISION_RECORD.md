# How this PointPillars project reached its current stage

**Project history, decisions, changes and evidence — 1–2 October 2026**

This document explains what we discussed, what changed, why each change was needed, where it lives, and what was actually checked. It follows the project from the first architecture request to Docker deployment, real-bag testing, RViz and the camera reference video.

It belongs beside the [A-to-Z deployment guide](PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex). That guide tells someone how to install and run the project. This history explains how we got there. The [chat discussion record](CHAT_DISCUSSION_RECORD.md) preserves the visible requests, progress updates and final replies from the original 35 available turns and the subsequent continuation, including the platform and artifact-location answers.

The record is based on the conversation, the current source, Git history, inventories and recovery evidence. It does not invent missing implementation work. Early plans and early replies describe earlier stages; the later source and dated results decide the current status. The supplied [project review](../PROJECT_REVIEW_AND_UPDATE_PLAN.md) was a starting reference, not another user instruction to carry out every proposal without checking it.

## Reading map

- [Where the project stands now](#where-the-project-stands-now)
- [1. The starting point and the first request](#1-the-starting-point-and-the-first-request)
- [2. Recovery when credits or a session run out](#2-recovery-when-credits-or-a-session-run-out)
- [3. Finding the GPU, models and actual software](#3-finding-the-gpu-models-and-actual-software)
- [4. TAO, TensorRT and why a pretrained model is not enough](#4-tao-tensorrt-and-why-a-pretrained-model-is-not-enough)
- [5. CPU geometry and ROS messages came first](#5-cpu-geometry-and-ros-messages-came-first)
- [6. The TensorRT runtime migration](#6-the-tensorrt-runtime-migration)
- [7. The completed download and the actual SDK installation method](#7-the-completed-download-and-the-actual-sdk-installation-method)
- [8. Building and running the ROS node, then adopting colcon](#8-building-and-running-the-ros-node-then-adopting-colcon)
- [9. Docker: from two commands to automatic deployment](#9-docker-from-two-commands-to-automatic-deployment)
- [10. The A-to-Z guide, Git exclusions and authentication](#10-the-a-to-z-guide-git-exclusions-and-authentication)
- [11. Moving the checkout and understanding quiet startup](#11-moving-the-checkout-and-understanding-quiet-startup)
- [12. Finding a ROS bag and inspecting the long output](#12-finding-a-ros-bag-and-inspecting-the-long-output)
- [13. Adding RViz visualization](#13-adding-rviz-visualization)
- [14. Preparing the bag and matching camera video automatically](#14-preparing-the-bag-and-matching-camera-video-automatically)
- [15. The Git milestones and the latest interruption](#15-the-git-milestones-and-the-latest-interruption)
- [16. The complete discussion route](#16-the-complete-discussion-route)
- [17. What was tested, and how far the evidence goes](#17-what-was-tested-and-how-far-the-evidence-goes)
- [18. Every changed source file: purpose, reason and location](#18-every-changed-source-file-purpose-reason-and-location)
- [19. The current operation, with each part's role](#19-the-current-operation-with-each-parts-role)
- [20. What still needs to happen](#20-what-still-needs-to-happen)
- [21. Artifact identity and how to follow the evidence](#21-artifact-identity-and-how-to-follow-the-evidence)

## Where the project stands now

The project can build a Docker image from published Git source, automatically obtain the selected model and TensorRT libraries, create an engine for the selected GPU, and run a ROS 2 inference node. A KITTI bag has passed through that node. RViz has displayed its point cloud and detection boxes. A helper now prepares the bag and a camera MP4 from the matching original drive.

This was physically exercised on Ubuntu 24.04 with an RTX 4060 Laptop GPU. The code does not hardcode that GPU. The image targets supported Linux x86-64 NVIDIA systems; a different supported GPU builds its own engine. We have not tested every PC or GPU. ARM and Jetson need another platform build, and Windows/WSL2 and macOS are outside the validated recipe.

The remaining gap is substantial: message flow and visualization work, but model accuracy has not been established. Class order, intensity normalization and box-coordinate conventions still need the export/training specification and a known reference sample. The bounded inference worker, configurable sensor QoS, timing metrics, benchmark and full operational/CI acceptance are also unfinished.

The checkout moved during the work. Its current location is:

~~~
/media/ae/New Volume/MasterThesis
~~~

Older messages and inventories refer to /home/ae/Desktop/MasterThesis. Those paths describe the original location. Because the current path contains a space, quote it in terminal commands.

As checked while preparing this record, local HEAD and public GitHub main both pointed to **dd687da7f42b4dc8fb53370be4a7c26635bc6e95**. The running inference image recorded that same source revision. Before this documentation work, .dockerignore and .gitignore still had local edits; the committed RViz and bag/video work was already published. Earlier “uncommitted” statements in progress logs are dated historical snapshots.

## 1. The starting point and the first request

You first asked for an efficient architecture, implementation steps and a way to recover when the model ran out of credits. When asked which platform to target, you chose **Ubuntu 24.04, ROS 2 Jazzy and an NVIDIA GPU**.

The repository we started from was a Foxy-era project. Its instructions described Ubuntu 20.04, TensorRT 8.2, an older TensorRT OSS build and hardcoded CUDA paths. The recorded Git baseline was 2301135. It could not simply be treated as a ready Jazzy/TensorRT 10 application.

The problems fell into three groups. The build mixed old compiler settings and platform paths. The ROS code needed newer message handling and clearer input validation. The GPU code assumed tensor binding positions, did not adequately check output sizes and used resource lifetimes that were difficult to trust.

There was also a geometry problem: overlapping boxes were filtered using code that needed protection against degenerate inputs and unstable calculations. Fixing installation alone would not address those issues.

The first deliverable was therefore a staged design in [IMPLEMENTATION_ARCHITECTURE.md](../IMPLEMENTATION_ARCHITECTURE.md), plus recovery tooling and a ledger. The initial reply explicitly said that C++ modernization was still planned. That distinction matters: an architecture document was not evidence that its proposed runtime had already been implemented.

### The architecture we chose

We separated three responsibilities:

1. A CPU core validates and filters detection boxes.
2. A ROS adapter turns PointCloud2 into a checked model input and turns checked boxes into Jazzy messages.
3. A GPU runtime loads a TensorRT engine and performs inference with resources it owns.

This separation lets us test geometry and malformed messages without a GPU, model or TensorRT SDK. It also keeps ROS message details out of inference internals and makes failures easier to locate.

The design proposed one GPU worker with one pending frame, so an overloaded application could retain recent data instead of building a long stale queue. That worker is **not yet implemented**. The current node still performs inference synchronously in callbacks and uses reliable delivery with queue depth 700. The architecture describes the destination as well as the work delivered so far.

The ordered milestones W00–W09 describe dependencies and acceptance criteria. Their states are summarized near the end of this document. Some independent packaging and visualization substeps were completed while broader prerequisite milestones remained open. That does not make the entire downstream milestone verified.

## 2. Recovery when credits or a session run out

We built [tools/recovery.py](../tools/recovery.py) before the larger migration. Its purpose is to preserve enough state for a later person or model session to continue without guessing what happened.

It records eligible source files, hashes, Git identity, separate staged and unstaged patches, task state, evidence and the next action. Completed checkpoints are immutable directories under .recovery/checkpoints. Temporary work is promoted only after the snapshot is complete. Status checks integrity and reports drift against the current tree.

The helper does not reset files, restore them automatically, stage a commit or change the Git index. It does not run tests or decide that a milestone passed. Evidence and state are assertions entered by the person using it. The acceptance result still needs the real command and result.

The defaults limit each text file to 1 MiB, the source snapshot to 16 MiB and each patch to 32 MiB. Symlinks are recorded without following them. Models, SDKs, engines, recordings, generated outputs, likely credential paths and oversized or binary files are excluded. These exclusions keep checkpoints small; they also mean a checkpoint is not a full backup of the machine.

The [resume guide](../recovery/RESUME.md), [progress record](../recovery/PROGRESS.md) and [task ledger](../recovery/tasks.json) give the next session a practical starting point. Recovery tests covered integrity, drift, interrupted checkpoints, changed Git state and preservation of the index. Twelve tests passed. A directory-to-file edge case found during review was corrected.

The actual continuation procedure is:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
python3 tools/recovery.py status
git status --short
git diff
git diff --cached
~~~

Read the recovery files, check whether an interrupted process is still running, preserve current changes and resume the unfinished substep. Before another coherent edit or long operation, save a checkpoint:

~~~bash
python3 tools/recovery.py checkpoint \
  --task W09 --state in-progress \
  --next 'Continue the interrupted substep and record actual verification.' \
  --evidence 'Current work remains unfinished.'
~~~

When credits ran out later, this mechanism helped preserve continuity. It cannot buy credits, change quota or keep an unavailable model working. A later session still needs access to the model. Local snapshots also cannot protect against loss of the disk; large assets and ignored verification logs need independent backups.

## 3. Finding the GPU, models and actual software

You next asked us to read the Markdown records and start implementation. When asked where the artifacts were, you answered **/home/ae/Downloads**. We inspected the files there rather than assuming the repository contained a usable runtime.

An early nvidia-smi call inside the restricted execution environment failed. A GPU-accessible check showed that the host driver and GPU actually worked. That first failure was a device-access limitation, not evidence that your computer needed a driver reinstall.

The observed host was Ubuntu 24.04.4 x86-64, ROS Jazzy, an RTX 4060 Laptop GPU with 8188 MiB reported memory, and driver 595.71.05. Host tools included GCC 13.3, CMake 3.28.3, Python 3.12.3 and CUDA compiler 12.0.140. Docker later used pinned CUDA 12.9 components. Host compiler version, driver capability and container CUDA version are different facts.

The model inventory identified a deployable ONNX and a trainable TLT file. The ONNX was used for engine generation. The TLT was hashed and inventoried; it was not decrypted, retrained or required for deployment.

The observed ONNX interface was:

| Tensor | Type | Shape |
|---|---|---|
| points | FLOAT32 | [batch, 204800, 4] |
| num_points | INT32 | [batch] |
| output_boxes | FLOAT32 | [batch, 393216, 9] |
| num_boxes | INT32 | [batch] |

The metadata reader in [tools/inspect_onnx_metadata.py](../tools/inspect_onnx_metadata.py) obtains these observations without pretending to be a full ONNX validator. Runtime parsing and actual engine creation supplied stronger evidence later.

The model also required three plugin creators, version 1, in the empty namespace:

- VoxelGeneratorPlugin
- PillarScatterPlugin
- DecodeBbox3DPlugin

We recorded the environment in [environment_inventory.json](../config/environment_inventory.json), the model in [model_inventory.json](../config/model_inventory.json), and the later SDK/engine observations in [runtime_inventory.json](../config/runtime_inventory.json). Those are observed inventories. The architecture's proposed environment.lock.json and model_contract.json are still not delivered final contracts.

## 4. TAO, TensorRT and why a pretrained model is not enough

You asked whether TAO was TensorRT and why another runtime was necessary when you already had a pretrained model.

**TAO** is NVIDIA's toolkit for training, adapting and exporting models. **TensorRT** prepares and runs inference on an NVIDIA GPU. They serve different parts of the workflow. Using the deployable pretrained export did not require us to train the model again.

The practical chain for this project is:

~~~
pretrained deployable ONNX
        ↓ TensorRT builder, with required plugins
GPU-specific engine
        ↓ project inference runtime
PointCloud2 → Detection3DArray
~~~

A pretrained model contains the learned computation. It does not supply the C++ headers, shared libraries, plugin creators, GPU driver, ROS message adapter or application lifecycle. The runtime still needs those pieces.

TensorRT's SDK includes development headers and libraries as well as tools such as trtexec. A local-repository DEB sets up a package source; it is not itself proof that all development packages have been installed. Python TensorRT installation alone also does not satisfy this project's C++ build.

The **engine** is the result of preparing the model for a selected GPU and software stack. We therefore moved engine creation to deployment startup, rather than treating one RTX 4060 engine as a universal file. NVIDIA documents the limits of engine portability in its [TensorRT support matrix](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/support-matrix.html). TAO's separate role is described in its [deployment overview](https://docs.nvidia.com/tao/tao-toolkit/latest/text/tao_deploy/tao_deploy_overview.html).

### Why we chose TensorRT 10.16.1 rather than the proposed 11.3 package

You proposed two downloads: TensorRT 11.3.0 and TensorRT 10.16.1, both for Ubuntu 24.04 with a CUDA 12.9 package variant.

The original code used TensorRT 8 APIs and the PointPillars export depended on legacy plugins. TensorRT 11 was not treated as a drop-in replacement. Moving to that major version would require another API/plugin compatibility investigation. The exact proposed 11.3 DEB was not validated in this work; we did not claim to have tested it. NVIDIA's [TensorRT 10-to-11 C++ migration documentation](https://docs.nvidia.com/deeplearning/tensorrt/latest/api/migration/tensorrt-10x-to-11x-c-api.html) explains why a major-version change needs care.

TensorRT 10.16.1 was a candidate, not an automatic guarantee. We first checked whether the three required creators were present, then whether the model parsed, then whether an engine built and actually ran. Those checks passed with **10.16.1.11**, CUDA 12.9 variant. All three plugins were already supplied by that SDK, so an OSS rebuild was unnecessary.

This choice was based on the model and demonstrated compatibility. “Newest” would not by itself have made deployment simpler or safer.

## 5. CPU geometry and ROS messages came first

While the full SDK download was pending, we completed work that did not depend on it.

### Geometry and output contracts

[src/postprocess.cpp](../src/postprocess.cpp) and [postprocess.h](../include/pp_infer/postprocess.h) became the independent CPU geometry layer. They validate boxes and filtering parameters, handle oriented overlap, avoid the problematic degenerate calculations and keep ties deterministic.

Class-agnostic suppression remains the default. The core exposes class-aware behavior, but it has not become a new ROS configuration option. Existing threshold behavior was retained where intended rather than silently changing the detection policy.

The output contract checks count bounds, row contents, class indexes, scores and finite positive dimensions before ROS publication. A malformed count must not become an unchecked memory copy or vector resize. These checks live in [output_contract.hpp](../include/pp_infer/output_contract.hpp) and have their own [test executable](../tests/runtime/test_output_contract.cpp).

Fifteen geometry cases and 2,000 randomized comparisons passed. Focused CPU AddressSanitizer and UndefinedBehaviorSanitizer checks also passed. LeakSanitizer was disabled in the traced environment, so that result does not establish leak checking.

### PointCloud2 validation

The ROS adapter in [src/pointcloud_adapter.cpp](../src/pointcloud_adapter.cpp) validates layout before converting or sending data to inference. It checks dimensions and byte arithmetic, row stride and padding, field offsets and types, byte limits and model point capacity.

For the current export, points need little-endian scalar FLOAT32 x, y, z and intensity fields. Organized clouds with valid row padding work. Malformed, oversized or capacity-exceeding messages are rejected. Nonfinite points are filtered, and intensity scaling is validated. A valid empty cloud produces an empty output without GPU inference.

The engine allows 204800 points. Docker's input-byte limit defaults to 64 MiB. The implementation rejects inputs beyond capacity; it does not silently truncate a larger cloud.

The adapter also brought the detection message construction into line with Jazzy's schema. The array and individual detections preserve the input header. Position and size describe the box; yaw becomes a quaternion. Class IDs and scores use the nested hypothesis fields expected by current vision_msgs.

Parameters such as scale and filtering limits have typed validation and are read-only after startup. Restart the node after changing them.

Eleven data fixtures and two local parameter cases passed in the normal ROS test build. An installed ROS allocator produced an ASan type-mismatch during node creation. We retained that limitation and ran parameter construction tests normally; instrumented data tests exclude node construction. We did not hide the error with a global sanitizer suppression.

### What the class names do and do not mean

The configuration currently uses class_0, class_1 and class_2 with intensity scale 1.0. That is a provisional smoke-test setting.

The added label.txt contains Vehicle, Pedestrian and Cyclist, but the available record does not establish who authored it or prove the model's ID order. The runtime does not turn that file into a verified export contract. RViz therefore colors numeric IDs rather than claiming semantic names.

The nine output columns are handled as x, y, z, length, width, height, yaw, class index and score. Structural validation does not establish whether the export's z is the center or another reference point, whether all axes match the sensor, or whether intensity should be divided by 255. Those questions need the training/export specification and reference data.

## 6. The TensorRT runtime migration

You explicitly authorized migration while the download continued. We used that time to replace the old TensorRT inference path and check compilation against official release headers. That first check was **compile-only**. It did not prove linking or GPU execution.

The main runtime work is in [src/pointpillar.cpp](../src/pointpillar.cpp), with its interface in [pointpillar.h](../include/pp_infer/pointpillar.h), shared model definitions in [model_contract.hpp](../include/pp_infer/model_contract.hpp), and CUDA ownership wrappers in [cuda_resources.hpp](../include/pp_infer/cuda_resources.hpp).

### Named tensors and startup checks

The runtime uses named tensors and enqueueV3 rather than relying on four binding positions. At startup it checks the expected tensor names, input/output roles, data types, shapes, supported profile, device storage and linear format.

It expects the supported batch-one engine contract. A file that happens to deserialize is not accepted merely because it has four tensors. Runtime compilation also requires TensorRT major version 10; a different major is not silently accepted.

The application runtime loads a serialized engine. It does not include a second ONNX engine builder inside every callback. The deployment entrypoint performs engine generation separately.

### Ownership and reusable resources

The TensorRT runtime, engine, execution context, logger and profiler have explicit lifetimes. CUDA buffers and a nonblocking stream are owned resources. The stream and four device buffers are reused across frames, as is host output storage.

Input padding is cleared, the point count is supplied explicitly and output count storage is reset for a frame. Copies and enqueue results are checked. This removes the old pattern of repeatedly allocating GPU resources and creating streams for each cloud.

The current output transfer is **count first**: copy the result count and synchronize the stream, validate the count, then copy only the required box rows and synchronize again. The architecture originally described a safe bounded whole-output transfer before later optimization. The implementation chose the checked count-first path. It is not a fully asynchronous pipeline.

CUDA or runtime-work failure faults the runtime, drains outstanding work during unwinding and rejects later inference until restart. The node currently catches errors, logs them and drops the affected frame. There is no completed supervisor that automatically replaces a faulted runtime or restarts the container.

### Corrections found with the real SDK

Several details were corrected only after actual SDK use:

- The version guard needed to handle TensorRT's macro aliases correctly.
- TensorRT 10.16 rejected setting the context profiler to null. The fix keeps the owned profiler alive and toggles collection. Profiler callback overhead is therefore not proven absent when collection is disabled.
- PCL/VTK-related C/MPI configuration was needed in the ROS build path, while the reduced CPU build stayed independent.
- ROS tests needed a writable log directory.
- ROS environment scripts needed temporary relaxation of shell nounset handling during entrypoint sourcing.

These are implementation fixes, not reasons to call all resource failure cases tested. More incompatible-engine and fault-injection coverage remains.

## 7. The completed download and the actual SDK installation method

When you said the download was complete, we inspected and hashed the roughly 5.17 GB TensorRT repository DEB. The early discussion had described a normal dpkg/keyring/apt installation. The method actually used on this machine changed because sudo required a password.

We extracted the outer DEB and selected component packages into a project-local SDK under .recovery/sdk/tensorrt-10.16.1. This supplied headers, shared libraries, plugins and trtexec without running package maintainer scripts or registering TensorRT in the host package database. Unused static libraries were omitted.

[tools/env_tensorrt.sh](../tools/env_tensorrt.sh) exposes the local include, library and executable paths. Sourcing it does not install packages. Its path handling supports the moved checkout.

The actual libraries reported all three required plugin creators. trtexec parsed the ONNX and built a batch-one FP32 engine with TF32 disabled and a 1024 MiB builder workspace. The native smoke engine is an ignored artifact under .recovery/engines. It is tied to the GPU/software stack that built it.

The full runtime then built and linked against the extracted SDK. A GPU smoke test exercised capacity rejection, ten synthetic frames, profiler toggling, empty output and destruction. CPU/ROS test modes also passed.

Compute Sanitizer 12.0 did not provide a usable GPU memory result. Initial library-path work did not resolve its instrumentation setup failure; it exited before meaningful checking. The record therefore says **inconclusive**, not “GPU memory checked.”

## 8. Building and running the ROS node, then adopting colcon

You asked us to build and run when everything was available. The first native launch used the runtime build artifact and produced a live synthetic PointCloud2 → TensorRT → Detection3DArray round trip with the header preserved. That sample returned one box; one synthetic box is an integration observation, not an accuracy metric.

You then asked for the node name and the correct command. ROS separates three names:

| Item | Current value |
|---|---|
| Package | pp_infer |
| Installed executable | pp_infer |
| Docker-configured node | /pointpillars |
| Native node without a name override | /minimal_publisher |
| Default input topic | /point_cloud |
| Default output topic | /bbox |

The command is **ros2 run PACKAGE EXECUTABLE**, so this project uses ros2 run pp_infer pp_infer. There is no ros2 node run command. A native invocation still needs a generated engine, parameter configuration and sourced environments.

You preferred colcon. We built the package with colcon, checked its installed executable and changed the current documentation to use colcon build, colcon test and colcon test-result. CMake remains the package backend; --cmake-args passes its configuration through colcon.

Reduced CPU, sanitized CPU and ROS builds use separate build/install directories so their options do not alter the normal runtime build. The CPU-only configuration intentionally has no install target. Its skipped-install warning is expected; its install directory is not an overlay for launching inference.

A representative native build, once host ROS, CUDA development files and the local SDK are ready, is:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
source /opt/ros/jazzy/setup.bash
source tools/env_tensorrt.sh
colcon build --packages-select pp_infer --cmake-args \
  -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
colcon test --packages-select pp_infer
colcon test-result --verbose
~~~

The full native dependency and engine-generation instructions are in the deployment guide. The old [launch/pp_infer_launch.py](../launch/pp_infer_launch.py) was not modernized; it still has historical absolute paths and unverified settings. It is not the validated startup method.

### Nodes, Docker images and camera pictures

You asked how to see node names and images on your machine. We explained ros2 node list, node info and topic list, as well as Docker's image/container inspection.

A Docker image packages a program and its dependencies. It is not a camera picture. This inference node publishes boxes from LiDAR points and has no camera-image output. rqt_image_view would need a separate camera image publisher. RViz is the appropriate viewer for the point clouds and 3D boxes, once a detection display plugin is available.

## 9. Docker: from two commands to automatic deployment

Your first packaging request was a Dockerfile that made the application usable with two commands. The first version used prepared local model/SDK inputs, built and tested with colcon, and put the runtime into a smaller final stage. Its two commands were docker build and docker run.

The image contained the ROS application, required shared libraries, plugins, model and engine-generation tool. Compilers remained in the build stage. GPU engine creation happened at runtime startup because the build did not need or assume access to the target GPU.

### Disk-space interruptions and recovery

Two packaging attempts encountered insufficient free space on the system filesystem. One large unused static SDK library was removed after your “done” response to the cleanup request. Later packaging also needed more space for Docker layers.

Automatic approval review could not initialize during those disk-full conditions. That was a storage failure, not a policy rejection of the project work. After space was available, work continued from the saved state.

We reduced the build footprint by installing only the required CUDA components and using shared TensorRT dependencies instead of pulling in large static development packages. We did not perform a blind Docker prune or move the entire Docker storage directory.

Moving the source later to another disk did not automatically move /var/lib/docker, images or build caches. Checking free space on the project disk alone is not enough when Docker stores layers elsewhere.

### Supporting different NVIDIA hardware

You specifically asked that the project work beyond the RTX 4060. We removed assumptions that one machine's engine was the deployment artifact.

[src/device_info.cpp](../src/device_info.cpp) provides pp_device_info, which reports the selected CUDA device and capability for startup checks. The same selected CUDA device is used by preflight, the builder and inference. Invalid selection fails clearly before normal startup.

The supported recipe uses capability 7.5 as a floor, enough GPU memory and the selected TensorRT 10/CUDA stack. A capability floor is necessary but not proof that every device and the legacy model plugins work together. Only the available RTX 4060 was physically checked. ARM/Jetson is a different build target.

The host supplies the driver and Docker GPU integration. Docker supplies application libraries. The guide describes a conservative CUDA 12.9 Update 1 driver target; it does not tell every machine to copy this laptop's driver number.

### Engine caching and interruption safety

[docker/entrypoint.sh](../docker/entrypoint.sh) checks the selected GPU and generates the engine there. It caches engines in the pp-engines volume using identity derived from the model hash, GPU UUID/capability, driver, CUDA API versions, TensorRT and build recipe.

The default recipe is batch-one FP32, no TF32 and 1024 MiB workspace. Workspace is a builder limit, not a cap on total GPU memory.

A file lock serializes builds for the same cache key. A temporary engine is renamed to its final cache path only on successful generation. An interrupted build therefore does not accept a partial output. A matching restart reuses the engine.

The checks exercised a fresh engine, two synthetic ROS/GPU round trips across restart and exactly one engine generation. An invalid GPU selection failed explicitly.

The cache does not yet automatically repair a later-corrupted nonempty engine file. If loading fails, identify and back up that file, remove only the identified cache entry and retry. Source checkpoints and engine caching solve different recovery problems.

### Your request for cloning, downloads and one command

You then wanted the Dockerfile to clone current Git, download the pretrained model, obtain TensorRT and everything else, build an engine and leave a node running.

We automated the build inputs in [Dockerfile](../Dockerfile). It now fetches published Git source with BuildKit's Git ADD, installs ROS Jazzy and pinned CUDA/TensorRT packages, downloads the selected NVIDIA NGC ONNX, verifies its SHA-256, builds/tests with colcon and records the source revision in the image.

It does not need your local extracted SDK, installer DEB, ONNX, engine or native build tree. The current .dockerignore restricts local context to Dockerfile and .dockerignore.

The automatic image uses TensorRT 10.16.1.11 packages consistently. An initial dependency attempt picked mismatched unpinned lean/dispatch/plugin dependencies and failed; those were explicitly pinned to the selected CUDA variant. Large static packages stayed out.

One part of the request needed a practical adjustment: **docker build cannot leave a persistent node running after its build containers exit**. [tools/deploy.sh](../tools/deploy.sh) supplies the real one-command workflow by building the image and then running it in the foreground:

~~~bash
sudo bash tools/deploy.sh
~~~

The wrapper stops before launch if the build fails. It refuses to replace an existing same-name container. It forwards configuration and extra build arguments, including a chosen Git reference. Engine generation remains startup work on the selected GPU, rather than becoming an unportable build-time asset.

An independent full build using the Dockerfile through stdin and an empty local context passed. This demonstrated that the automatic downloads did not accidentally depend on an ignored local model or SDK.

The source inside the image is **published Git source**, not whatever uncommitted files happen to be in your working folder. Push a runtime change before rebuilding it this way. For a reproducible source choice, pin PP_GIT_REF to a full commit SHA. Ubuntu base tags and ROS apt packages can still change; source pinning alone is not a fully immutable dependency supply chain. Retain the built image if you need that exact deployment.

## 10. The A-to-Z guide, Git exclusions and authentication

You asked for a natural-language LaTeX document that a nontechnical person could follow, from driver setup through node launch, and asked us to update README accordingly.

We created [PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex](PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex), preserved the old instructions in [LEGACY_FOXY_README.md](LEGACY_FOXY_README.md), and revised [README.md](../README.md) around the current Jazzy workflow.

The guide covers terminology, host checks, Ubuntu drivers, Docker, NVIDIA Container Toolkit, source/model/SDK preparation, Docker operation, ROS inspection, sensor/bag input, synthetic checks, image transfer, native development, recovery, troubleshooting and remaining work. Later edits added the automatic-download route, moved path, RViz and bag/video helper.

Driver and Docker/GPU integration were already working on this host. The guide's fresh-host installation commands are reproduction instructions; this work did not reinstall your driver or exercise every fresh-host installation block.

You later requested colcon everywhere. We changed the current build/test instructions and executed the documented reduced configurations: two CPU tests, two sanitized CPU tests and four normal ROS modes passed. Historical logs still contain the direct CMake/CTest commands actually used earlier; rewriting them would falsify that history.

The built-in LaTeX compiler was called after guide edits, but its environment could not retrieve an uncached TeX bundle or closed the sandbox connection before parsing. Command and link checks passed; **PDF compilation and layout remain unverified**. We preserved the source and editor rather than installing a separate terminal TeX distribution or creating a replacement PDF. This new history is Markdown so it can be read without that compiler.

### Keeping large files out of Git

You asked us not to forget large files before pushing. [.gitignore](../.gitignore) excludes SDK/recovery directories, colcon outputs, model weights/exports, TensorRT engines, installer packages, bags, source/container archives, generated media, Python caches, partial downloads and generated LaTeX outputs.

The checks confirmed that the large TensorRT DEB, ONNX/TLT files, Docker assets and extracted SDK were ignored. At that inspection, no Git-eligible file exceeded 10 MiB and no model/SDK binary was staged. Editable source, LaTeX, configuration and recovery records remain eligible.

Later bag/video work added data and video/partial-file patterns. Dedicated demo asset folders also receive their own ignore file. Ignore rules prevent new additions; they do not automatically remove already-tracked files from Git history. There was no identified already-tracked large asset needing removal in the recorded check.

The agent gave review/stage/commit/push instructions but did not make those commits or pushes. You subsequently published them. The Git milestones are recorded below.

### Avoiding repeated GitHub username/password prompts

You asked how to stop repeated GitHub prompts. The observed remote used HTTPS and had no credential helper configured. We recommended GitHub CLI browser authentication and Git's CLI credential integration:

~~~bash
sudo apt update
sudo apt install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
git push
~~~

This was advice, not a completed authentication action performed by the agent. We did not install gh, log into your account, configure SSH keys or store a password on your behalf. GitHub describes this approach in its [credential-caching documentation](https://docs.github.com/en/get-started/git-basics/caching-your-github-credentials-in-git).

## 11. Moving the checkout and understanding quiet startup

You told us the project had moved and authorized continuation. We found the moved tree at /media/ae/New Volume/MasterThesis, checked Git and checkpoint integrity, and continued there.

Scripts and new commands quote paths with spaces. The SDK environment helper resolves its current location. Native generated build caches, install setup files and engine-path parameters can still contain old absolute paths, so they need fresh build directories or regeneration. Historical inventories deliberately retain the paths where their evidence was recorded.

You then posted Docker export output followed by GPU, capability, UUID and CUDA API information and asked why it stopped.

Inspection showed that the container and /pointpillars node were running. A cached engine had been reused, and no point-cloud publisher was supplying input at that moment. The foreground terminal was attached to a running node waiting for data. Image export had completed; quiet startup was not evidence of a failed build or hung engine generator.

Use a second terminal to inspect it:

~~~bash
sudo docker ps
sudo docker logs --tail 80 pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 node list
sudo docker exec pointpillars /entrypoint.sh ros2 node info /pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 topic list -t
~~~

The container does not generate real LiDAR data. A separate sensor driver or bag player is required.

You also asked whether anyone could simply clone and run deploy.sh, and whether this was documented. The answer was conditional: a supported Ubuntu/Linux x86-64 NVIDIA host must already have a suitable driver, Docker, NVIDIA Container Toolkit, network access and enough space. After those host prerequisites, clone and the wrapper are the application route. README and the guide explain that boundary; the image is not a universal installer for every operating system or GPU.

## 12. Finding a ROS bag and inspecting the long output

You asked for a bag to test the current status. We found the public KITTI sequence04 ROS 2 conversion, corresponding to drive **2011_09_30_drive_0016_extract**. The converter/dataset mapping is published by [kitti_to_ros](https://github.com/Jakubach/kitti_to_ros) and its [bag dataset](https://huggingface.co/datasets/kubchud/kitti_to_ros).

The bag archive is about 502 MB; the extracted database is about 856 MB. It contains 283 LiDAR clouds and IMU messages. It does **not** contain the camera images needed for the later video request.

Its LiDAR topic is /velodyne_points. Playback remaps that to /point_cloud. The current subscription requests reliable delivery, so the playback uses an explicit reliable QoS override. A best-effort-only live publisher can appear in the graph without matching this node; configurable sensor QoS remains pending.

The first recommendation supplied manual download, extraction, bag inspection and playback commands. At that point, recommending the bag was not a claim that it had already been tested. Later playback and inspection supplied the evidence.

### What the printed detections meant

You pasted a long Detection3DArray output, then asked us to inspect it ourselves because it was too long.

The output contained header/frame information, a box center and dimensions, orientation quaternion, hypotheses with numeric class IDs and scores, and an empty tracking ID. An empty ID is expected because the node has no tracking implementation.

The frame was velodyne. Timestamps from 2011 were the recorded sensor times; they were not a current system-clock failure. The weaker scores visible at the end of a long array did not describe every box in that array.

We then subscribed to the running input and output and checked matched headers, cloud layout and capacity, finite box values, positive dimensions, normalized quaternions, valid class indexes and score bounds.

Inside Docker, 25 matched real-bag frames had 125007–126701 points and 65–97 boxes per frame, with scores approximately 0.10027–0.65835. A later host-transport check matched another 25 frames, with 83–109 boxes per frame and a maximum score around 0.70379. No invalid messages were found in those checks.

The counts differ because the checks sampled different frames. They are short integration samples, not a sustained throughput benchmark. Plausible boxes and valid messages do not prove correct detections against labeled ground truth.

## 13. Adding RViz visualization

Before this step, the project published Detection3DArray but did not supply a ready viewer. We added a saved RViz configuration, numeric class colors and a launcher:

- [rviz/pointpillars.rviz](../rviz/pointpillars.rviz)
- [rviz/class_colors.yaml](../rviz/class_colors.yaml)
- [tools/visualize.sh](../tools/visualize.sh)

The viewer uses the official [vision_msgs RViz Detection3DArray plugin](https://github.com/ros-perception/vision_msgs/blob/ros2/vision_msgs_rviz_plugins/README.md). We did not add a marker converter to inference.

Host RViz was already installed, but that display plugin was missing. Because sudo needed a password, the official package was downloaded using the configured ROS apt index and extracted into ignored .recovery/rviz. That did not register a system package. The launcher first supports a system-installed plugin, then provides this local extraction path if possible. Missing dependencies still need a proper host installation.

The plugin bootstrap and CLI startup were also checked in a temporary checkout whose path contained spaces.

### Why the viewer needed a transport change

The first host subscriber did not receive container data through default Fast DDS shared memory. The root-container and desktop-user ownership arrangement caused a local transport problem. UDPv4 received data successfully.

The launcher therefore defaults FASTDDS_BUILTIN_TRANSPORTS to UDPv4 while allowing an explicit caller setting to override it. This is an observed fix for this host/container arrangement, not a guarantee that firewalls, domains or discovery settings elsewhere need no attention. Fast DDS documents its transport settings in the [transport reference](https://fast-dds.docs.eprosima.com/en/v2.14.7/fastdds/transport/transport.html).

Live RViz rendering showed the point cloud and colored box edges. The fixed frame is velodyne for the tested bag. A global TF warning was recorded because this sensor-frame-only playback supplied no transform tree. Points and boxes still shared the same frame and rendered. We did not invent a world transform to hide the warning.

Points use intensity coloring. Boxes use orange for numeric ID 0, blue for 1 and yellow for 2. These are visual identifiers, not verified class labels. Scores are hidden in the default view but can be enabled by expanding Detections. The viewer adds no confidence filter. Its configured render rate is not an inference benchmark.

### Your questions about what visualize.sh actually does

You asked whether visualization was only for rosbag testing. It can also show compatible live LiDAR and detections. The data source can change; the viewer needs matching topics, frame, ROS domain and network discovery.

You then asked whether visualize.sh only opens RViz. Yes: it prepares the optional display plugin and opens the saved view. It does **not** start inference, download a bag or begin playback.

With inference and a source already running:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
bash tools/visualize.sh
~~~

For another sensor frame/domain:

~~~bash
ROS_DOMAIN_ID=7 bash tools/visualize.sh -f your_lidar_frame
~~~

Custom topic names must also be reflected in the RViz displays. The inference image remains headless; a Docker-only runtime host does not need host ROS or a GUI. The optional viewer does.

## 14. Preparing the bag and matching camera video automatically

You asked for another shell file to download, prepare and start the rosbag, plus a video so you could understand the scene. We created:

- [tools/rosbag_demo.sh](../tools/rosbag_demo.sh), the user-facing prepare/start/stop wrapper.
- [tools/prepare_kitti_demo.py](../tools/prepare_kitti_demo.py), the download, integrity, extraction and video preparation logic.
- [docker/demo-tools.Dockerfile](../docker/demo-tools.Dockerfile), a small preparation image with Python and FFmpeg.
- [tests/test_kitti_demo.py](../tests/test_kitti_demo.py), focused recovery and range-download tests.
- [config/demo_inventory.json](../config/demo_inventory.json), the asset and validation record.

Using a separate preparation image avoids installing Python/FFmpeg libraries across each host. Playback uses the already-built inference image's ROS tools but does not itself need GPU access.

Default assets live beside the project, not inside Git:

~~~
/media/ae/New Volume/rosbags/kitti04
~~~

The helper accepts a dedicated custom folder through PP_DEMO_DIR and checks unsafe or unsupported bind-path choices. It uses a preparation lock and preserves file ownership for the invoking user.

Its modes are:

~~~bash
bash tools/rosbag_demo.sh prepare
bash tools/rosbag_demo.sh start
bash tools/rosbag_demo.sh stop
~~~

The default with no argument is start. Prepare obtains assets without starting playback. Start prepares/reuses assets, inspects the bag and starts looping only the LiDAR topic. Stop accepts only a helper-labeled playback container.

The default player is pointpillars-bag, domain 0, rate 0.5, reliable QoS and /velodyne_points remapped to /point_cloud. A matching active player is reused. An incompatible or stopped same-name container is preserved and reported rather than silently replaced.

During validation, stop correctly refused an earlier manually started player. That was expected ownership protection, not a helper failure. At the later documentation snapshot, the user had restarted playback with the helper and its ownership label was present. The earlier progress statement describing the manual player remains historical.

### Download integrity and interrupted preparation

The ROS bag URL is pinned to dataset revision 410f471b4995acc94f728a9c590fb7645eff376e. The helper verifies the bag ZIP hash, extracted member sizes/CRCs and expected SQLite topic.

Downloads use partial files and validation before promotion. Focused tests cover resumable downloads, completed pending-file promotion, changed remote objects, incorrect/truncated ranges and preservation of corrupt completed archives. Corrupt assets are reported rather than quietly accepted.

Camera images come from the original matching KITTI raw drive, because the ROS bag has no camera images. The raw archive is roughly 1.72 GB. Instead of downloading every sensor, the helper reads the ZIP directory and requests byte ranges for the left color camera frames and timestamps. It checks HTTP ranges and pins the remote ETag, then verifies extracted frame CRCs.

The recorded camera preparation transferred 598075104 bytes, including range-block overhead, rather than the full 1724245728-byte archive. It retains at most four 1 MiB range blocks in memory, and completed frames can be reused after an interruption. This is a bounded range cache, not a promise that only compressed image bytes are ever transferred.

### What the video represents

FFmpeg uses the camera timestamp intervals to make a variable-frame-rate H.264 MP4, pads odd image dimensions for yuv420p and prepares it for playback. A pending output is probed before becoming the final clip. Timestamp files and asset manifests remain beside the clip.

The prepared video is kitti04_left_camera.mp4: 1392×512, approximately 29.72 seconds and 24 MB. It uses 285 source camera frames; concat's final-duration handling repeats the last frame. Full video decoding passed, and a frame was visually inspected.

The first camera timestamp is 0.210053376 seconds before the first LiDAR timestamp. The raw camera frames are unsynchronized/unrectified, and there are 285 camera frames versus 283 LiDAR scans. KITTI explains its raw-data variants and sensors on its [official dataset page](https://www.cvlibs.net/datasets/kitti/raw_data.php).

The video gives scene context. It is **not annotated ground truth**, is not automatically synchronized with ROS playback, does not project detection boxes into camera pixels and is not published as a ROS camera topic. The bag's default half-speed playback and the video's recorded-speed playback will drift unless you manually account for their different timing; changing playback speed alone does not create exact synchronization.

Eight focused HTTP/download/timestamp tests passed. Actual camera preparation, MP4 decoding and isolated-domain bag playback were also exercised. In ROS domain 99, a test player supplied three valid reliable clouds, then helper-owned stop succeeded. Repeat preparation reused the validated assets without repeating the camera download or encoding.

## 15. The Git milestones and the latest interruption

The repository now records three main publication steps after the old baseline:

| Commit | Recorded local time, 2 October 2026 | Commit subject | What it captures |
|---|---|---|---|
| 8747cc77ceddcdbda5514e390a11395b8dd71aca | 11:03 | Modernize PointPillars runtime, Docker deployment and documentation | The runtime/build modernization and initial deployment documentation. |
| ee07c5681e8c7266177f203313eea09a56a63f62 | 12:11 | Modify the docker file, documentation | Automatic Git/model/SDK deployment and corresponding instructions. |
| dd687da7f42b4dc8fb53370be4a7c26635bc6e95 | 13:26 | feat: add RViz visualization and reproducible KITTI bag/video setup | Viewer and reproducible bag/camera preparation. |

You asked for a suitable commit name, and we suggested the subject used in the final row. The commits were made and published by you; the agent did not commit or push on your behalf.

During the first history-writing attempt, the model reached its usage limit again. The chat record had already been written, but the narrative draft was still in the tool session. When you asked us to continue, that session storage was no longer available. The project disk was also unmounted.

We located the unmounted volume, mounted it through the normal disk service without formatting or forcing a filesystem repair, found the saved chat document, and recovered the narrative text from this thread's local session record. We then saved it as a real file before continuing. This is another reason to checkpoint coherent work to disk instead of relying on a model's session memory.

This history adds documentation, README links and an updated continuation record. It does not alter the inference algorithm, re-run GPU benchmarks or turn the remaining milestones into completed work.

## 16. The complete discussion route

Times in this table use Europe/Berlin, UTC+02:00 on these dates. They indicate when the turn started, not when every operation in it finished. Follow each turn link for its recorded requests and replies.

| Turn | Date and time | What you asked or clarified | Result and where it is explained |
|---|---|---|---|
| [1](CHAT_DISCUSSION_RECORD.md#turn-1--1-october-2026-at-2148) | 1 Oct, 21:48 | Architecture, efficient implementation steps and credit recovery; chose Ubuntu 24.04/Jazzy/NVIDIA. | Staged architecture and tested recovery, sections 1–2. C++ still planned at that point. |
| [2](CHAT_DISCUSSION_RECORD.md#turn-2--1-october-2026-at-2201) | 1 Oct, 22:01 | Read records and implement; identified Downloads as the artifact location. | Inventory plus CPU/ROS implementation, sections 3 and 5. |
| [3](CHAT_DISCUSSION_RECORD.md#turn-3--1-october-2026-at-2230) | 1 Oct, 22:30 | Is TAO TensorRT, and why is TensorRT needed for a pretrained model? | Separate training/export and inference roles, section 4. |
| [4](CHAT_DISCUSSION_RECORD.md#turn-4--1-october-2026-at-2234) | 1 Oct, 22:34 | TensorRT 11.3 package suitability. | Larger API/plugin migration; exact package not validated, section 4. |
| [5](CHAT_DISCUSSION_RECORD.md#turn-5--1-october-2026-at-2240) | 1 Oct, 22:40 | TensorRT 10.16.1 package suitability. | Candidate chosen subject to real plugin/parser/runtime checks, sections 4 and 7. |
| [6](CHAT_DISCUSSION_RECORD.md#turn-6--1-october-2026-at-2242) | 1 Oct, 22:42 | Required SDK/development-header and build/run steps. | Explained repository package versus full SDK and ordered checks, sections 4 and 7; full commands remain in the deployment guide. |
| [7](CHAT_DISCUSSION_RECORD.md#turn-7--1-october-2026-at-2249) | 1 Oct, 22:49 | What to do while the SDK downloads. | Independent source migration could proceed; full linking waited, section 6. |
| [8](CHAT_DISCUSSION_RECORD.md#turn-8--1-october-2026-at-2250) | 1 Oct, 22:50 | Start migration and recovery checkpoints during the download. | Named tensors, ownership and checks; compile-only evidence first, section 6. |
| [9](CHAT_DISCUSSION_RECORD.md#turn-9--1-october-2026-at-2311) | 1 Oct, 23:11 | Download completed. | Local SDK extraction, actual plugins/engine, build/link and smoke checks, section 7. |
| [10](CHAT_DISCUSSION_RECORD.md#turn-10--2-october-2026-at-0008) | 2 Oct, 00:08 | Build and run the node if prerequisites exist. | Native node and synthetic ROS/GPU round trip, section 8. |
| [11](CHAT_DISCUSSION_RECORD.md#turn-11--2-october-2026-at-0010) | 2 Oct, 00:10 | Node name and correct ROS command. | Package/executable/node distinction and ros2 run, section 8. |
| [12](CHAT_DISCUSSION_RECORD.md#turn-12--2-october-2026-at-0011) | 2 Oct, 00:11 | Prefer colcon build. | Installed colcon route and checks, section 8. |
| [13](CHAT_DISCUSSION_RECORD.md#turn-13--2-october-2026-at-0013) | 2 Oct, 00:13 | See node names and images. | ROS/Docker inspection and camera-image distinction, section 8. |
| [14](CHAT_DISCUSSION_RECORD.md#turn-14--2-october-2026-at-0014) | 2 Oct, 00:14 | Current and remaining progress. | Integration versus accuracy/performance acceptance, sections 17 and 20. |
| [15](CHAT_DISCUSSION_RECORD.md#turn-15--2-october-2026-at-0016) | 2 Oct, 00:16 | Dockerfile for two commands. | Packaging began; interrupted turn continued later, section 9. |
| [16](CHAT_DISCUSSION_RECORD.md#turn-16--2-october-2026-at-0923) | 2 Oct, 09:23 | Continue after credits and support other NVIDIA hardware. | Storage obstacle and per-GPU engine approach, section 9. |
| [17](CHAT_DISCUSSION_RECORD.md#turn-17--2-october-2026-at-0927) | 2 Oct, 09:27 | Cleanup done; continue. | Docker build, runtime checks and restart-cache evidence completed, section 9. |
| [18](CHAT_DISCUSSION_RECORD.md#turn-18--2-october-2026-at-1003) | 2 Oct, 10:03 | Natural A-to-Z LaTeX guide and README, including fresh-host deployment. | Guide created, compiler limitation recorded, section 10. |
| [19](CHAT_DISCUSSION_RECORD.md#turn-19--2-october-2026-at-1051) | 2 Oct, 10:51 | Use colcon instead of direct CMake in documentation. | Current commands updated and reduced workflows exercised, sections 8 and 10. |
| [20](CHAT_DISCUSSION_RECORD.md#turn-20--2-october-2026-at-1058) | 2 Oct, 10:58 | Ignore large files before pushing. | Artifact exclusions and size checks, section 10. |
| [21](CHAT_DISCUSSION_RECORD.md#turn-21--2-october-2026-at-1104) | 2 Oct, 11:04 | Avoid repeated GitHub credential prompts. | GitHub CLI/browser credential advice, section 10. |
| [22](CHAT_DISCUSSION_RECORD.md#turn-22--2-october-2026-at-1117) | 2 Oct, 11:17 | Clone published edits and automatically obtain model/SDK/engine, with one command. | Automatic build inputs plus build/run wrapper; another space obstacle, section 9. |
| [23](CHAT_DISCUSSION_RECORD.md#turn-23--2-october-2026-at-1141) | 2 Oct, 11:41 | Continue from the moved project. | Moved-path reconciliation and completed automatic deployment, section 11. |
| [24](CHAT_DISCUSSION_RECORD.md#turn-24--2-october-2026-at-1212) | 2 Oct, 12:12 | Full overview for this PC. | Host prerequisites and application operation, sections 11 and 19 and the deployment guide. |
| [25](CHAT_DISCUSSION_RECORD.md#turn-25--2-october-2026-at-1220) | 2 Oct, 12:20 | Why startup seemed stopped after GPU information. | Running node awaiting input, section 11. |
| [26](CHAT_DISCUSSION_RECORD.md#turn-26--2-october-2026-at-1225) | 2 Oct, 12:25 | Can another PC clone and run deploy.sh? | Supported-host conditions and physical-testing limit, sections 9 and 11. |
| [27](CHAT_DISCUSSION_RECORD.md#turn-27--2-october-2026-at-1226) | 2 Oct, 12:26 | Is portability/setup covered in documentation? | README and guide coverage confirmed, sections 10–11. |
| [28](CHAT_DISCUSSION_RECORD.md#turn-28--2-october-2026-at-1227) | 2 Oct, 12:27 | Find a suitable test rosbag. | KITTI sequence04 source, layout, remap and reliable QoS, section 12. |
| [29](CHAT_DISCUSSION_RECORD.md#turn-29--2-october-2026-at-1237) | 2 Oct, 12:37 | Supplied the long detection output. | Box/hypothesis/header interpretation, section 12. |
| [30](CHAT_DISCUSSION_RECORD.md#turn-30--2-october-2026-at-1240) | 2 Oct, 12:40 | Inspect output directly, then assess/add RViz. | Matched real frames, host transport fix and live rendering, sections 12–13. |
| [31](CHAT_DISCUSSION_RECORD.md#turn-31--2-october-2026-at-1301) | 2 Oct, 13:01 | Is visualization only for bag testing? | Compatible live LiDAR can also be viewed, section 13. |
| [32](CHAT_DISCUSSION_RECORD.md#turn-32--2-october-2026-at-1301) | 2 Oct, 13:01 | Does visualize.sh only open RViz? | It prepares the plugin and opens the view; source/inference remain separate, section 13. |
| [33](CHAT_DISCUSSION_RECORD.md#turn-33--2-october-2026-at-1303) | 2 Oct, 13:03 | Add bag initialization/download script and matching scene video. | Docker preparation tools, pinned data, range downloads, MP4 and recovery checks, section 14. |
| [34](CHAT_DISCUSSION_RECORD.md#turn-34--2-october-2026-at-1325) | 2 Oct, 13:25 | Suggest a commit name. | The RViz/bag/video commit subject, section 15. |
| [35](CHAT_DISCUSSION_RECORD.md#turn-35--2-october-2026-at-1329) | 2 Oct, 13:29 | Document the entire conversation, every edit, its purpose and location. | This history plus the chat record and README links. The first attempt hit the usage limit. |
| [36](CHAT_DISCUSSION_RECORD.md#turn-36--continuation-after-the-usage-limit) | 2 Oct, 14:28 | Continue after another usage interruption. | Drive reconnected, narrative recovered and saved, documentation completed, section 15. |

The original 35-turn export retains historical answers and visible progress updates, including installation alternatives and commands later superseded. The continuation entry records this latest interruption. Repeated editor selections were context, not separate requests to rewrite everything shown.

## 17. What was tested, and how far the evidence goes

These results were collected during the implementation. This documentation update checks their records and source coverage; it does not claim to rerun the whole application.

| Check | Recorded result | What it establishes | What it does not establish |
|---|---|---|---|
| Recovery fixtures | 12 passed | Snapshots, drift/integrity handling and preservation of Git state in the tested cases. | Full-machine backup, automatic quota continuation or recovery from disk loss. |
| CPU geometry | 15 cases and 2000 randomized comparisons passed | Tested overlap/NMS behavior and validation. | Detector accuracy or GPU execution. |
| CPU sanitizers | Focused ASan/UBSan passed | Tested CPU paths under instrumentation. | LeakSanitizer coverage, which was unavailable in the traced environment. |
| ROS adapters | 11 data and two parameter cases passed normally | Tested layout/parameter/message behavior locally. | End-to-end DDS delivery by itself; node-construction ASan issue remains recorded. |
| Runtime output contract | Invalid count/class/score/box cases passed | Checked handling of malformed output rows/counts. | Every incompatible engine or CUDA failure scenario. |
| Official-header compilation | Syntax checks passed before the SDK arrived | The migration compiled against the selected release API headers. | Linking, plugins or GPU inference at that stage. |
| Actual SDK/runtime | Full build/link and ten synthetic frames passed | The selected model/plugins/engine execute on the observed GPU. | Real-data accuracy or every resource-failure case. |
| Native ROS/GPU flow | Synthetic header-preserving round trip passed | Live ROS input reached inference and produced matching output. | Accuracy from the observed one-box sample. |
| Colcon documentation workflows | CPU 2, sanitized CPU 2, normal ROS 4 modes passed | The reduced current build/test commands work on this host. | Fresh-host driver/SDK installation. |
| Docker builds | Four colcon modes passed; Dockerfile-only empty-context full build passed | Packaged source/dependencies and automatic fetch path actually build. | All future apt/base changes or every other machine. |
| Engine restart | Fresh generation and two round trips; exactly one generation across restart | Cache reuse and successful startup on this GPU. | Universal engine portability or automatic corrupted-cache repair. |
| Selection/conflict guards | Invalid GPU failed clearly; wrapper conflict returned expected exit 1 | Checked guards preserve existing named containers. | Full crash supervision or restart policy. |
| Real KITTI integration | 25 matched frames in Docker plus 25 via host UDPv4, without invalid messages | Real cloud layout, matched output and host transport work in those samples. | Labeled accuracy, long-run throughput or overload acceptance. |
| RViz | Live points and boxes rendered; isolated plugin bootstrap passed | The official display/plugin and saved viewer work on this desktop. | Camera overlays or verified class semantics. |
| Demo recovery | Eight focused tests passed | Range/ETag, partial-download, corrupt-asset and timestamp behavior in the fixtures. | Every server/proxy/network combination. |
| Actual data preparation | Pinned bag checks, public camera extraction/encoding and full MP4 decode passed | The prepared assets are usable; repeat preparation reuses them. | Automatic camera/LiDAR synchronization or ground truth. |
| Isolated player | Three valid clouds in domain 99; helper-owned stop passed | Playback/remap/reliable QoS and ownership guard work in that check. | A long inference benchmark. |
| CUDA memory instrumentation | Inconclusive; setup failed before meaningful instrumentation | A recorded tool limitation. | A passed GPU memory-safety check. |
| LaTeX compiler | Failed before source parsing | Source is retained and tool failure is recorded. | Compiled PDF correctness or visual layout. |

Exact commands, exit codes and log hashes are indexed in [tasks.json](../recovery/tasks.json) and the inventories. Most raw logs, engines, SDK libraries and screenshots are under ignored .recovery/verification or other ignored directories. Cloning Git alone will not copy those evidence artifacts.

### The main corrections and dead ends

Several earlier choices were revised as evidence improved:

| Earlier situation | Correction | Why it changed |
|---|---|---|
| Restricted nvidia-smi failed. | Checked outside the restriction and found the working GPU/driver. | Sandbox device access was not host-driver health. |
| System TensorRT apt installation was discussed. | Extracted a local SDK for native work. | Sudo needed a password; local extraction supplied the required files without host registration. |
| Only SDK headers were available initially. | Later required real link, plugin, parser and GPU checks. | Syntax-only success cannot establish runtime compatibility. |
| TensorRT version check assumed a simpler macro form. | Corrected macro-alias handling. | Real 10.16 headers exposed the issue. |
| Profiling disable attempted a null profiler. | Kept the owned profiler and disabled collection. | Actual TensorRT 10.16 rejected the null operation. |
| ROS parameter-node construction hit a system ASan allocator mismatch. | Retained the limitation and tested that path normally. | Suppressing it globally would misrepresent instrumented coverage. |
| Compute Sanitizer failed to initialize. | Recorded GPU memory checking as inconclusive. | No meaningful instrumentation ran. |
| Docker initially needed local SDK/model inputs. | Downloaded pinned packages/model inside the build. | You asked for a clone-and-deploy route. |
| TensorRT secondary dependencies were not fully pinned. | Pinned lean/vc/dispatch dependencies to the same selected variant. | Initial dependency resolution failed. |
| Builds filled the root disk. | Reduced unused static/CUDA build footprint and continued after identified cleanup. | Source on another disk does not relocate Docker layers. |
| Strict shell settings conflicted with ROS setup scripts. | Relaxed nounset only while sourcing them. | Entrypoint needed to load the ROS environment correctly. |
| Host Fast DDS shared memory delivered no clouds. | Defaulted the viewer to UDPv4. | The tested root-container/desktop-user arrangement worked through UDP. |
| Missing host RViz vision display plugin. | Downloaded/extracted the official package locally; documented normal apt installation. | RViz existed, but the Detection3DArray display did not. |
| Sensor-only bag had no world TF tree. | Kept the correct common sensor frame and documented the warning. | Inventing a transform would hide missing information. |
| Original player was manually started. | Helper refused to stop it; later helper-started playback carried its own label. | Container ownership must be explicit. |
| Built-in LaTeX environment failed before parsing. | Preserved editable source and reported PDF unverified. | The failure was not resolved by claiming a successful PDF. |
| Latest draft was only in session storage when quota stopped. | Recovered it from the local session record and saved it to disk. | Session memory did not survive the continuation. |

## 18. Every changed source file: purpose, reason and location

This index covers **all 51 paths changed or added between baseline 2301135 and published dd687da**. A path appearing in the diff does not prove the agent authored every line: the supplied review and label file have the attribution limits noted below. The existing dirty ignore edits are also explained. The two new history documents and this turn's continuation updates follow the table.

Paths link into the repository so they remain useful after cloning to another computer.

### Build, packaging and operating settings

| File | What changed | Purpose and reason |
|---|---|---|
| [.dockerignore](../.dockerignore) | Began with a source/local-asset allowlist; the current local edit allows only Dockerfile and .dockerignore. | Keep large local SDK/model/build artifacts out of the context now that the Dockerfile fetches inputs itself. |
| [.gitignore](../.gitignore) | Added recovery, colcon, SDK/model/engine/archive/bag/generated-document/cache/media/partial-data exclusions. | Keep Git and checkpoints focused on editable project material; preserve independent large assets on disk. |
| [CMakeLists.txt](../CMakeLists.txt) | Uses C++17, separate CPU/ROS/runtime targets and build switches, TensorRT 10 checking, explicit dependencies, tests and installed executables. | Make colcon/native/Docker builds consistent and allow CPU work without GPU libraries. CMake remains the backend. |
| [package.xml](../package.xml) | Updated package dependency declarations for the current ROS message/build path. | Make the package describe what the Jazzy source actually needs. |
| [Dockerfile](../Dockerfile) | Multistage Jazzy/CUDA/TensorRT build, remote published source, pinned SDK components, checksum-verified ONNX, colcon tests and runtime packaging. | Supply application inputs automatically, keep compilers out of the final stage and avoid a build-time GPU requirement. |
| [docker/entrypoint.sh](../docker/entrypoint.sh) | Sources environments; offers utility execution; selects/checks GPU; locks/builds/caches engines; starts the configured node. | Use one GPU selection consistently and recover safely from interrupted engine generation. |
| [docker/node.yaml](../docker/node.yaml) | Supplies provisional smoke/deployment parameters, with startup providing engine_path. | Remove reliance on historical launch paths while making unresolved model semantics explicit. |
| [docker/demo-tools.Dockerfile](../docker/demo-tools.Dockerfile) | Adds a separate Ubuntu preparation image with Python, FFmpeg and CA dependencies. | Download/prepare datasets and video without installing those libraries on every host. |

### Inference, geometry and ROS adapters

| File | What changed | Purpose and reason |
|---|---|---|
| [include/pp_infer/cuda_resources.hpp](../include/pp_infer/cuda_resources.hpp) | Owned device-buffer and stream helpers with checked CUDA operations. | Make resource lifetime and cleanup explicit; reuse resources across frames. |
| [include/pp_infer/model_contract.hpp](../include/pp_infer/model_contract.hpp) | Shared input/box contract definitions and limits used across boundaries. | Avoid scattering assumptions about capacities and row structure through ROS and runtime code. These are structural definitions, not verified training semantics. |
| [include/pp_infer/output_contract.hpp](../include/pp_infer/output_contract.hpp) | Checked output counts and row decoding/validation. | Reject impossible counts and malformed boxes before memory copies/publication. |
| [include/pp_infer/pointpillar.h](../include/pp_infer/pointpillar.h) | Updated runtime interface and internal implementation ownership. | Keep TensorRT implementation detail behind a clearer inference boundary. |
| [include/pp_infer/postprocess.h](../include/pp_infer/postprocess.h) | GPU-independent geometry/filtering interface with explicit box representation. | Make geometry testable in a reduced CPU build. |
| [include/pp_infer/ros_adapter.hpp](../include/pp_infer/ros_adapter.hpp) | Adapter/configuration interface for validated clouds and detections. | Keep message validation and Jazzy mapping independent of real GPU execution. |
| [src/device_info.cpp](../src/device_info.cpp) | Added installed pp_device_info CUDA preflight utility. | Report the selected device/capability/API identity instead of hardcoding the development GPU. |
| [src/pointcloud_adapter.cpp](../src/pointcloud_adapter.cpp) | Validates layout, bounds, fields, scale and finite values; handles padding/empty clouds and constructs detections. | Prevent malformed ROS input from becoming unsafe or misleading model data. |
| [src/pointpillar.cpp](../src/pointpillar.cpp) | TensorRT 10 named-tensor startup, owned engine/context/profiler, reusable buffers/stream, checked count-first transfer and fault state. | Replace old binding-index/lifetime assumptions with checked inference on the selected stack. |
| [src/postprocess.cpp](../src/postprocess.cpp) | Validated oriented overlap/clipping, deterministic ordering and safe suppression. | Correct geometry edge cases and isolate CPU correctness from installation issues. |
| [src/pp_inference_node.cpp](../src/pp_inference_node.cpp) | Integrates adapters/runtime, typed read-only configuration, Jazzy publication and frame-error reporting. | Make the ROS node consume checked data and preserve headers. Its callback is still synchronous; worker/QoS work remains. |
| [label.txt](../label.txt) | Added Vehicle, Pedestrian and Cyclist strings in the published tree. | This is an observed added file, with authorship and model-ID order unproven in the chat. It is not wired as a verified runtime class contract. |

### User-facing tools

| File | What changed | Purpose and reason |
|---|---|---|
| [tools/deploy.sh](../tools/deploy.sh) | Builds published Git source then foreground-runs the image; passes settings and rejects name conflicts. | Give the requested one-command application workflow without pretending docker build can keep a node running. |
| [tools/env_tensorrt.sh](../tools/env_tensorrt.sh) | Exposes the project-local SDK paths relative to the script location. | Support native builds without registering host TensorRT packages, including paths with spaces after relocation. |
| [tools/inspect_onnx_metadata.py](../tools/inspect_onnx_metadata.py) | Reads ONNX interface/operator metadata for inventory. | Find tensor capacities/plugins before attempting a full engine build; avoid calling metadata inspection full validation. |
| [tools/prepare_kitti_demo.py](../tools/prepare_kitti_demo.py) | Pinned/resumable bag download, ZIP integrity/extraction, object-pinned camera range reads, timestamps, video preparation and manifests. | Make the demonstrated data preparation repeatable and resumable without downloading every raw sensor. |
| [tools/recovery.py](../tools/recovery.py) | Checkpoint/status CLI with hashes, patches, caps, exclusions and atomic completion. | Preserve interrupted development without resetting current files or relying on model memory. |
| [tools/rosbag_demo.sh](../tools/rosbag_demo.sh) | Docker preparation/player wrapper with prepare/start/stop, settings, locks, ownership and conflict guards. | Initialize and replay the tested bag while protecting unrelated/manual containers. |
| [tools/visualize.sh](../tools/visualize.sh) | Host RViz launcher, optional official plugin extraction, environment paths, frame argument and UDPv4 default. | Open a working desktop point/box view while leaving inference and source playback separately controlled. |

### Tests

| File | What changed | Purpose and reason |
|---|---|---|
| [tests/core/test_postprocess.cpp](../tests/core/test_postprocess.cpp) | Geometry/NMS edge cases and randomized comparisons. | Check CPU behavior without needing ROS, CUDA or the model. |
| [tests/ros/test_ros_adapter.cpp](../tests/ros/test_ros_adapter.cpp) | Cloud-layout/data fixtures, Jazzy detection construction and parameter validation. | Check malformed/organized/empty/oversized input and message behavior locally. |
| [tests/runtime/runtime_smoke.cpp](../tests/runtime/runtime_smoke.cpp) | Actual-engine repeated inference, capacity/profiler/empty-output/destruction checks. | Exercise the real selected GPU runtime beyond successful compilation. |
| [tests/runtime/test_output_contract.cpp](../tests/runtime/test_output_contract.cpp) | Invalid count, class, score and box cases. | Check output handling safely in the CPU test path. |
| [tests/test_kitti_demo.py](../tests/test_kitti_demo.py) | Eight range/object-change/resume/corruption/timestamp fixtures using a local HTTP server. | Test recovery behavior that is difficult to dependably provoke on a public server. |
| [tests/test_recovery.py](../tests/test_recovery.py) | Twelve checkpoint/drift/integrity/index-preservation fixtures. | Test the continuation mechanism before relying on it through interruptions. |

### Visualization assets

| File | What changed | Purpose and reason |
|---|---|---|
| [rviz/class_colors.yaml](../rviz/class_colors.yaml) | Numeric-ID box colors. | Distinguish ID groups without inventing verified semantic class names. |
| [rviz/pointpillars.rviz](../rviz/pointpillars.rviz) | Saved PointCloud2 and Detection3DArray displays, sensor fixed frame, reliable QoS and viewing settings. | Make the tested points/boxes easy to open together rather than manually rebuilding the display layout. |

### Evidence inventories

| File | What changed | Purpose and reason |
|---|---|---|
| [config/environment_inventory.json](../config/environment_inventory.json) | Observed host/software/GPU facts. | Separate measured environment facts from proposed lock/contract files. |
| [config/model_inventory.json](../config/model_inventory.json) | Model hashes, size, interface and custom operators. | Identify the actual export and its requirements before migration. |
| [config/runtime_inventory.json](../config/runtime_inventory.json) | Selected SDK packages/plugins, local engine and smoke evidence. | Record the native compatibility result; old paths remain historical evidence. |
| [config/docker_inventory.json](../config/docker_inventory.json) | Docker image/source/environment and validation log hashes. | Identify the tested packaging snapshots instead of assuming a mutable image tag is a fixed artifact. |
| [config/visualization_inventory.json](../config/visualization_inventory.json) | Official plugin identity, host transport/real-frame results and screenshot/log references. | Support the claim that the viewer was actually exercised. |
| [config/demo_inventory.json](../config/demo_inventory.json) | Bag/camera provenance, hashes, counts/timing, helper image and validation references. | Make dataset preparation traceable and distinguish video context from accuracy evidence. |

### Documentation and continuation records

| File | What changed | Purpose and reason |
|---|---|---|
| [IMPLEMENTATION_ARCHITECTURE.md](../IMPLEMENTATION_ARCHITECTURE.md) | Staged CPU/ROS/GPU design, worker proposal, gates and recovery protocol. | Explain the implementation order and proposed end state; some early observations are now historical. |
| [PROJECT_REVIEW_AND_UPDATE_PLAN.md](../PROJECT_REVIEW_AND_UPDATE_PLAN.md) | Supplied review included in the published tree. | Starting reference retained. Its Git addition is not evidence that the agent wrote it or implemented every recommendation. |
| [README.md](../README.md) | Current Jazzy quick start, host conditions, automatic deployment, bag/video, viewer, limits and recovery links. | Replace outdated first-contact instructions with the usable current routes. |
| [docker/README.md](../docker/README.md) | Explains automatic fetch/build/start, settings, source pinning, cache portability and optional viewer/data helper. | Describe Docker's responsibility and its host prerequisites clearly. |
| [docs/LEGACY_FOXY_README.md](LEGACY_FOXY_README.md) | Preserves the original Foxy/TensorRT 8 instructions. | Retain project history without presenting old commands as today's setup. |
| [docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex](PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex) | A-to-Z natural-language guide, later updated for colcon, automatic downloads, moved path, RViz and demo helper. | Let another person reproduce the deployment and understand its limits. PDF compilation is still unverified. |
| [docs/local_runtime.md](local_runtime.md) | Native SDK/engine/build record and current colcon route, with relocation caveats. | Keep the native development setup traceable alongside Docker deployment. |
| [recovery/PROGRESS.md](../recovery/PROGRESS.md) | Dated work, corrections, exact checks and limitations. | Provide a durable implementation record rather than relying on a conversational claim. |
| [recovery/RESUME.md](../recovery/RESUME.md) | Current checkout, continuation commands and blockers. | Let the next session resume safely instead of repeating completed work. |
| [recovery/tasks.json](../recovery/tasks.json) | Milestones/dependencies, states, acceptance targets, next actions and evidence references. | Track partial completion and prevent integration checks from becoming an accuracy/performance claim. |

### Files and artifacts outside that 51-path change list

The unchanged launch/pp_infer_launch.py still contains the legacy startup path; we did not deliver a revised production launch package. LICENSE, CLA.md and the old images remain baseline material. No CI workflow, benchmark tool, final model contract, camera publisher, tracker or camera-box projection was quietly added.

Generated artifacts include the local SDK, native engines, colcon outputs, Docker images/volumes, official RViz plugin extraction, logs, screenshots, bag database, camera PNGs/timestamps/manifests and MP4. They are large or environment-specific and are kept outside eligible source snapshots. Their purpose and integrity are recorded without putting them all in Git.

This documentation turn adds [PROJECT_HISTORY_AND_DECISION_RECORD.md](PROJECT_HISTORY_AND_DECISION_RECORD.md) and [CHAT_DISCUSSION_RECORD.md](CHAT_DISCUSSION_RECORD.md), links them from README, and updates continuation/progress/ledger notes to recognize the published dd687da revision. It preserves the previous local ignore edits. It does not rewrite older inventory snapshots to make them appear freshly measured.

## 19. The current operation, with each part's role

For a fresh supported computer, first follow the [deployment guide](PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex) to prepare the host driver, Docker and NVIDIA Container Toolkit. The build image cannot install the host kernel driver or give Docker host GPU access.

Once those prerequisites are ready, the application source can be obtained with:

~~~bash
git clone https://github.com/AhmedAliMohammed1/MasterThesis.git
cd MasterThesis
sudo bash tools/deploy.sh
~~~

On this machine, use the existing checkout instead:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
sudo bash tools/deploy.sh
~~~

Check for an existing pointpillars container first. The wrapper deliberately refuses that conflict; it does not replace a running node. Stop/remove only the intended old instance after inspecting it, or choose another PP_CONTAINER_NAME with suitable topics/domain.

The deploy command remains attached to the running node. Use another terminal for the data source:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
bash tools/rosbag_demo.sh
~~~

Then, on the ROS Jazzy desktop with RViz available, use another terminal for visualization:

~~~bash
cd '/media/ae/New Volume/MasterThesis'
bash tools/visualize.sh
~~~

These are separate jobs:

| Job | What it does | What it expects |
|---|---|---|
| deploy.sh | Builds published application source and starts GPU inference. | Prepared Docker/GPU host, network/build storage, no conflicting container. |
| rosbag_demo.sh | Obtains sample assets/video and starts or reuses compatible playback. | Docker; inference image already built for playback. |
| visualize.sh | Prepares the display plugin if possible and opens RViz. | Host ROS/RViz, desktop session, matching topics/frame/domain and running input/output. |
| Camera MP4 | Shows the matching drive's recorded scene in a video player. | Prepared file; synchronization with ROS is manual and not guaranteed. |

Use utility commands inside the existing container without starting a second inference instance:

~~~bash
sudo docker exec pointpillars /entrypoint.sh ros2 pkg executables pp_infer
sudo docker exec pointpillars /entrypoint.sh ros2 node list
sudo docker exec pointpillars /entrypoint.sh ros2 topic info /point_cloud --verbose
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /bbox --once
sudo docker exec pointpillars /entrypoint.sh cat /opt/pp_infer/source-revision.txt
~~~

For a live LiDAR, replace the bag player with its manufacturer-specific driver. Input must meet the validated XYZI layout, point/byte limits and reliable QoS requirement. Set the input topic/domain for inference and match the RViz frame/topics. There is no universal sensor-driver command.

Docker runtime parameters live in docker/node.yaml. A mounted edited copy can be used; restart after changing read-only parameters. Startup supplies the engine path. The guide explains image transfer using docker save/load so a runtime-only host does not need source, host ROS, host TensorRT or the CUDA development toolkit.

To stop helper-owned playback and the intended inference container:

~~~bash
bash tools/rosbag_demo.sh stop
sudo docker stop pointpillars
~~~

Close RViz separately. The bag helper refuses to stop an unlabeled manual player; inspect that case explicitly. Stopping one project component is not permission to prune unrelated images, volumes or containers.

## 20. What still needs to happen

The recovery ledger remains the task authority. Its overall states are:

| Task | State | Delivered and remaining |
|---|---|---|
| W00 — architecture/recovery | Verified | Design and local recovery mechanism tested. |
| W01 — platform/model contract | Blocked | GPU/SDK/plugins/engine observed; class order, normalization, coordinates and known reference still missing. |
| W02 — CPU geometry | Verified | Reduced geometry tests and focused CPU sanitizers passed. |
| W03 — ROS adapters | Verified locally | Data/parameter/message fixtures passed, with the system allocator instrumentation limitation recorded. |
| W04 — runtime ownership/validation | In progress | Build/link and synthetic execution passed; additional incompatible-engine and resource-failure checks remain. |
| W05 — buffers/safe inference | In progress | Reusable resources and checked output flow implemented; memory/failure and reference acceptance remain. |
| W06 — bounded worker | Pending | One worker and a bounded pending-frame policy still need implementation. |
| W07 — configuration/QoS/metrics | In progress | Viewer and bag/camera helper delivered independently; full launch, sensor QoS and metrics depend on further work. |
| W08 — benchmark/optimization | Pending | Numerical targets, representative accuracy/overload replay and 30-minute resource/thermal evidence remain. |
| W09 — operational guide/CI | In progress | Build/deployment guide and packaging delivered; clean-machine/other-hardware, supervisor/rollback, CI and PDF acceptance remain. |

The next useful step is obtaining the export/training contract and a labeled reference fixture. Without them, changing labels or intensity scaling would replace one assumption with another. Use the fixture to check coordinate conventions and expected detections.

Then finish runtime failure/memory checks, implement the bounded worker, expose sensor QoS deliberately, add timing/drop/resource metrics and agree on measurable acceptance targets. The ledger still has many null performance/accuracy targets; a maximum input capacity is not the same thing as an agreed operating rate.

Only after those targets exist should we claim real-time behavior or choose optimizations such as FP16. A short live demonstration and a viewer's render rate are not a benchmark. Relevant checks also need to be repeated on each intended target GPU and on a clean deployment host.

The current project is an implemented and demonstrated inference/deployment path with a usable viewer and reproducible sample preparation. It is not yet a completed accuracy-validated, benchmarked production system.

## 21. Artifact identity and how to follow the evidence

The hashes below identify important observed inputs/results. They are not instructions to share an engine with every computer.

| Artifact | Recorded identity |
|---|---|
| Deployable ONNX, 5572374 bytes | SHA-256 2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1 |
| Trainable TLT, inventoried only | SHA-256 4e901182d10f40023bd5924ef8d5b7eca493901fc80029582a4c2abaf33e4f2f |
| TensorRT 10.16.1 local-repository DEB, 5168856786 bytes | SHA-256 9f465423f47e739c1db159cb9dd2c8991cbff13380e1a358476c40321bff07fe |
| Native FP32 smoke engine, 8965628 bytes | SHA-256 422de0884b89c665f4133ef86dab4f8d8eceb3d4c3d502a1861410d7f7a24f23 |
| Pinned bag dataset revision | 410f471b4995acc94f728a9c590fb7645eff376e |
| Bag ZIP, 501598025 bytes | SHA-256 6903a1c3f68cf327cbbd2f579803184c6158ef8a1c41c086b26a85d5cc84cecd |
| Camera raw ZIP, 1724245728 bytes | ETag 78d1f40e3341bd7ae246e49d6ed12094-206; member CRC checks used. |
| Prepared MP4, 24343762 bytes | SHA-256 e7fa83d3f5adab18eee2868fa0543146cb6d22a2c50745659ce16dc5da96d685 |
| Inference image observed at the first history snapshot | sha256:347eca6be6b86fb06d2a538a44d09398f2a0bc6af41f04ddbd8be983ba184a1b |
| Source recorded in that running image | dd687da7f42b4dc8fb53370be4a7c26635bc6e95 |

Image tags such as pp-infer:jazzy-trt10 can point to a different image after a rebuild. The source-revision file and immutable image ID are more useful provenance. Older JSON inventories describe their earlier images and paths; they were not replaced with the later identity without a new corresponding test run.

Use the inventories for structured details, PROGRESS.md for the dated implementation record, tasks.json for acceptance and next actions, and the chat record for the exact visible discussion. The source links above identify every changed file in the published implementation range. This combination preserves both the reasoning behind the project and the evidence for its present stage.
