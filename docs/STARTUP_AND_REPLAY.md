# Deployment and Ouster replay fixes — 8 November 2026

The reported startup failure had three independent mismatches: the live launcher
subscribed to `/ouster1/points` on domain 0 through Zenoh, but the downloaded bag
published `/sensing/lidar/points` on domain 99 through Fast DDS. No Zenoh router
was running. Visibility across these configurations cannot be assumed.

Use the explicit **bag** profile for the downloaded MOSEP recording. Both scripts
now obtain defaults from `tools/ouster_profile.sh`: Fast DDS, domain 99,
`/sensing/lidar/points`, and saved image `pp-infer:jazzy-trt10`. The adapter's
output is `/point_cloud` and detections are `/bbox`. Explicit environment overrides
remain supported; repeat the same overrides in both terminals because sudo may
discard exports. The existing bare `start_ouster.sh` remains the live-sensor
profile (Zenoh/domain 0/`/ouster1/points`) and needs a working driver and router.

## Build once, then start the downloaded recording

From the checkout, build/check the image without launching a detector:

```bash
sudo env PP_BUILD_ONLY=1 bash tools/deploy.sh
```

`PP_BUILD_ONLY=1` is optional. Without it, deployment starts the detector only;
stop that detector with Ctrl+C before starting the combined Ouster pipeline.
Deployment itself does not start the adapter, bag player or RViz.

Terminal 1:

```bash
sudo bash tools/start_ouster.sh bag
```

Terminal 2:

```bash
sudo bash tools/start_ouster_bag.sh
```

Terminal 3, on the graphical desktop, without sudo:

```bash
ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  RVIZ_CONFIG="$PWD/rviz/ouster.rviz" \
  bash tools/visualize.sh -f lidar/os_lidar
```

The adapter uses reflectivity / 255. The bag's original payload and file contents
are unchanged, and the bag is mounted read-only. The recording calls its signal
channel `intensity`, so do not select `signal` for this unchanged recording.
`rain30` and `rain100` remain available on `start_ouster_bag.sh`.

If an old container still occupies either name, inspect it and stop only the
intended instance before restarting. Scripts do not replace existing containers.
For normal repeat runs, skip deployment entirely and use terminals 1–3.

## Build reuse and drivers

`deploy.sh` checks host `nvidia-smi` and Docker before building. It does not install
or upgrade host NVIDIA drivers. CUDA/TensorRT/ROS inside the image are separate
from the host driver; finding a host library does not make it available in an
isolated container.

The default source is now the local checkout, including uncommitted runtime edits.
Only a narrow runtime-source whitelist is sent to Docker. The saved image has a
checksum label covering those inputs. Matching inputs reuse the existing image
without invoking Docker build. README/docs-only edits do not affect that checksum.
Changed C++/configuration/Docker inputs trigger a build using the existing Docker
layer cache. Model downloads and dependency installations are independent of source
COPY, and the source revision argument is declared after dependency installation.
Missing/pruned cache, dependency recipe changes or a deliberately refreshed base
can still require installations/downloads. No promise of offline first builds is
made.

- `PP_FORCE_BUILD=1`: run a build even if the saved checksum matches, preserving cache.
- `PP_PULL_BASE=1`: explicitly refresh base images; this can invalidate dependencies.
- `PP_BUILD_ONLY=1`: stop after preparing the image.
- `PP_SOURCE_MODE=remote`: build published Git source. Setting `PP_GIT_REF` or
  `PP_GIT_REPO` also selects remote mode unless source mode is explicitly set.

Remote mode resolves the chosen Git source on each requested build. Direct
Dockerfile builds retain their remote-source default. Local builds record both
checkout revision and runtime-input checksum; a reused image may retain an older
Git revision after a documentation-only commit while its runtime inputs match.

## One Ctrl+C

All four host launchers now use `tools/docker_foreground.sh`. The host waits on
the Docker client with an interruptible Bash wait. One SIGINT invokes Docker stop
for the exact container ID created by that run, allowing up to eight seconds for
shutdown before Docker's forced termination. It never stops an unrelated container
by a reused name. An interrupt returns exit status 130. The Ouster supervisor
still stops both process groups and their descendants.

The image entrypoint also runs the inference executable directly, removing the
intermediate `ros2 run` Python process. Engine generation has signal handling that
terminates the builder and removes a partial `.pending` engine. Successful cached
engines and the named volume remain intact. Entry-point changes require rebuilding
an image; host-side stop handling applies immediately to the saved images.

## The MCAP metadata warning

`Metadata record with name 'rosbag2' did not contain key 'serialized_metadata'`
comes from reading the publisher's older MCAP metadata with the installed player.
The original `metadata.yaml` is present. In our actual replay the warning did not
prevent cloud publication or processing. It is not a missing-point-cloud-field
error. The source file is preserved; no bag rewrite or warning suppression is used.

## Validation

The final local-source test image built successfully with all seven C++/ROS tests
passing. All 91 Python tests passed outside the filesystem/network sandbox; six
existing download tests require localhost sockets. The shutdown unit test also
passed after the private cidfile-directory change.

In a real GPU replay, the matching-default scripts delivered 20 observed raw
clouds, 20 adapted clouds and 19 detection arrays. Sampled adapter and detector
counters reported zero rejections, invalid inputs or inference errors. One SIGINT
per launcher removed its own container in 0.490 s (player) and 0.487 s (pipeline).
No extra interrupts or manual container stops were needed. All test containers
were removed, and the saved production image was left unchanged.

The final dependency/model stages were cached with no apt download lines; another
unchanged deployment skipped Docker build entirely. The test image is
`pp-infer:launcher-fix-test`. Results and source hashes are in
[`config/launcher_fix_validation.json`](../config/launcher_fix_validation.json).
The original bag was replayed from a read-only mount. These checks establish
startup/replay/shutdown behavior, not detection accuracy.
