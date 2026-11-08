# Live Ouster adapter

> **New measured channel decision — 8 November 2026:** 1,120 current-production GPU observations now include independent Ouster object annotations. Reflectivity/255 has stronger vehicle BEV evidence than signal/65535 on the frozen subset; neither has qualifying 3D accuracy. Both complete the tested numerical runs. See [results, limitations and proposal](OUSTER_CHANNEL_DECISION.md). Older unlabeled Ouster observations below retain their original scope.

**Fresh GPU/RViz test — 7 November 2026:** a separately downloaded MOSEP Ouster
bag was replayed unchanged through the combined launcher and GPU detector, with
RViz opened on the desktop. Publisher checksum and source hashes passed; live
conversion and detection-header checks passed. See
[the fresh visual test](FRESH_OUSTER_VISUAL_TEST.md) for results, provenance and
restart commands. Earlier sandbox-only verification limits below describe those
earlier checks, not this later host execution.

The `ouster_adapter` executable adds a separate, GPU-independent input layer:

```text
/ouster1/points (original Ouster PointCloud2)
    -> ouster_adapter (validate + numeric channel conversion)
    -> /point_cloud (FLOAT32 XYZI)
    -> pointpillars -> /bbox
```

The Ouster driver and original topic are unchanged. Use the combined launcher
below, or start the adapter and detector separately. The adapter subscribes only to the configured input, lists discovered
PointCloud2 topics, and logs the actual accepted field layout. It does not
automatically choose between sensors, merge clouds, or create transforms. Run
`ros2 topic list -t` for the complete ROS graph, including IMU and other topics;
only point-cloud topics are relevant to this adapter.

## Start the complete pipeline with one command

With the Ouster driver already running and a saved GPU image containing the
adapter, run from the checkout:

```bash
sudo bash tools/start_ouster.sh                # reflectivity / 255.0
# Or choose signal / 65535.0 instead:
sudo bash tools/start_ouster.sh signal
```

This starts one foreground container containing the adapter and detector, reusing
the normal engine cache. Ctrl+C stops both and removes the container. If either
process exits, the other and its child processes are stopped too. The launcher
checks that the adapter executable exists in the image before GPU startup. It
refuses an existing container with the same name and never replaces one.

The defaults match the documented live host: Zenoh, domain 0, input
`/ouster1/points`, adapted output `/point_cloud`, detections `/bbox`, confidence
threshold 0.4, and builder workspace 512 MiB. Match your actual driver settings:

```bash
sudo env OUSTER_POINT_CLOUD_TOPIC=/ouster2/points \
  RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=7 \
  bash tools/start_ouster.sh reflectivity
# Raw numeric conversion, with no division beyond 1.0:
sudo env PP_OUSTER_INTENSITY_DIVISOR=1.0 bash tools/start_ouster.sh signal
```

`OUSTER_POINT_CLOUD_TOPIC` is the raw driver input; `POINT_CLOUD_TOPIC` is the
adapted topic consumed by the detector. They must differ. `PP_IMAGE`,
`PP_CONTAINER_NAME`, `PP_ENGINE_VOLUME`, `DETECTIONS_TOPIC`, `PP_GPU_INDEX`,
`PP_WORKSPACE_MIB` and `PP_CONFIDENCE_THRESHOLD` work as with `tools/start.sh`.
`PP_OUSTER_INTENSITY_SOURCE` selects the source when no positional source is given;
`PP_OUSTER_INTENSITY_DIVISOR` overrides that source's default divisor. See
`bash tools/start_ouster.sh --help` for all defaults.

The launcher mounts `docker/ouster_stack.sh` read-only from this checkout to
supervise both processes. Keep that file alongside the launcher. Host ROS is
unnecessary. It does not build/pull an image or start/reconfigure the sensor
driver. It always converts the explicitly selected channel; automatic XYZI
passthrough and choosing a feature based on model accuracy are not implemented.

**Existing images need an update to contain the adapter.** Build directly from
the current checkout without starting a detector:

```bash
sudo env PP_BUILD_ONLY=1 bash tools/deploy.sh
```

Then use `start_ouster.sh` for live input or `start_ouster.sh bag` for the downloaded
recording. The latter shares the bag player's Fast DDS/domain 99/raw-topic defaults.
Local builds no longer require a Git push. Remote-source mode still requires
publishing changes. The engine volume is retained across launches.

## Conversion choices

One model intensity value can come from either source. The adapter never blends
signal and reflectivity, falls back to a different field, or rescales each frame
by its observed maximum. Select the source and divisor explicitly:

| Configuration | Formula | Interpretation |
| --- | --- | --- |
| Default: `reflectivity`, divisor `255.0` | `float(reflectivity) / 255.0` | Initial comparison setting for the documented UINT8 live reflectivity field |
| `signal`, divisor `65535.0` | `float(signal) / 65535.0` | Numeric range normalization for the documented UINT16 signal field |
| Either source, divisor `1.0` | Numeric conversion only | Preserves the channel's raw numeric values |

These settings establish message compatibility, **not validated model training
parity or detection accuracy**. Signal and reflectivity have different meanings.
Integer-to-float conversion reads the original value; it does not relabel its
bytes. No clipping is applied. For older drivers with UINT16 reflectivity, the
divisor remains explicit; its appropriate value must be established from that
driver's data and the model contract. FLOAT32 source channels are also supported.
Legacy recorded bags that call their signal field `intensity` should continue
using the existing replay tools; this live adapter deliberately requires the
selected `signal` or `reflectivity` field.

Output has exactly four scalar FLOAT32 fields `x/y/z/intensity`, point_step 16,
and compact rows. Header, frame ID, dimensions, point order and XYZ bytes are
preserved. Input row padding is supported. Auxiliary fields remain available on
the original input topic; they are omitted from the adapted cloud. Nonfinite XYZ
is preserved with `is_dense=false` and removed by the existing detector's input
adapter. Negative/nonfinite channel values or FLOAT32 overflow reject the entire
cloud. Zero-range points are preserved; geometric filtering is a separate issue.

The adapter rejects missing/duplicate/nonscalar required fields, unsupported
types/endian, overlapping selected fields, invalid offsets, inconsistent row/data
lengths, and capacity violations before conversion. It rechecks every message.
Defaults are 204800 points and 67108864 bytes, matching the current detector's
documented limits. Match `max_points` to any future engine's actual capacity.

## Build and run without a GPU

From the checkout, use a separate build/install folder so existing builds remain
available:

```bash
source /opt/ros/jazzy/setup.bash
colcon --log-base .recovery/ouster-adapter-log build --packages-select pp_infer \
  --build-base .recovery/ouster-adapter-build \
  --install-base .recovery/ouster-adapter-install \
  --cmake-args -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=ON \
    -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/usr/bin/python3
source .recovery/ouster-adapter-install/setup.bash
# Match the middleware and domain used by your Ouster drivers:
export RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_DOMAIN_ID=0
ros2 launch pp_infer ouster_adapter_launch.py \
  input_topic:=/ouster1/points output_topic:=/point_cloud \
  intensity_source:=reflectivity intensity_divisor:=255.0
```

This build needs installed ROS Jazzy development dependencies, including the
project's existing PCL dependencies, but no CUDA, TensorRT, ONNX or engine. The
launch file starts only the adapter. Stop it with Ctrl+C. To compare signal, stop
that instance and repeat with `intensity_source:=signal intensity_divisor:=65535.0`.
Conversion parameters are read-only after startup to keep an experiment stable.

The normal full GPU build also installs this executable. In an image rebuilt
from source containing this change, the adapter can run in its own container:

```bash
sudo docker run --rm --init --network host --name ouster-adapter \
  -e RMW_IMPLEMENTATION=rmw_zenoh_cpp -e ROS_DOMAIN_ID=0 \
  pp-infer:jazzy-trt10 ros2 run pp_infer ouster_adapter --ros-args \
  -p input_topic:=/ouster1/points -p output_topic:=/point_cloud \
  -p intensity_source:=reflectivity -p intensity_divisor:=255.0
```

Older images may not contain the adapter. `deploy.sh` builds current local runtime
source by default; use `PP_BUILD_ONLY=1` to prepare the image without starting.
Direct remote-source Dockerfile builds still require a published change. No image rebuild or deployment is performed just by
editing this checkout.

Start the detector using the adapted topic and the same middleware/domain:

```bash
sudo env RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_DOMAIN_ID=0 \
  POINT_CLOUD_TOPIC=/point_cloud bash tools/start.sh
```

The saved detector image can consume this standard XYZI output without a detector
code update. Its `intensity_scale` should be `1.0` (the supplied node YAML's
default) to avoid scaling twice. Do not simultaneously publish a bag or another
adapter to the same output topic. For two sensors, use distinct adapter node names
and output topics; no two-sensor fusion is implemented.

## Inspect reception and conversion

```bash
ros2 node info /ouster_adapter
ros2 topic info /ouster1/points --verbose
ros2 topic echo /ouster_adapter/stats --once
ros2 topic echo /point_cloud --field fields --once
ros2 topic echo /bbox/stats --once
```

The adapter requests best-effort sensor QoS, compatible with best-effort or
reliable publishers under DDS. It publishes reliable XYZI with depth 5 for the
existing reliable detector subscription. Middleware implementations must match
across drivers, adapter and detector; this does not bridge Zenoh and DDS.

Diagnostics arrive every two seconds, including `received`, `converted`,
`rejected`, selected channel/divisor, last accepted schema, input publisher count,
and discovered PointCloud2 topics with publishers. A malformed latest cloud reports ERROR; an interval without
incoming clouds reports WARN. Counters are cumulative for the adapter process.
Accepted subsequent scans recover conversion. A topic visible in discovery does
not prove that messages arrive, and an adapted cloud does not prove inference or
accuracy; inspect detector counters separately.

Implementation: `src/ouster_adapter.cpp` performs conversion;
`src/ouster_adapter_node.cpp` owns subscriptions, discovery and diagnostics;
`tests/ros/test_ouster_adapter.cpp` tests conversions, rejection controls,
compatibility with the actual detector packer, and synthetic ROS transport.

## Local verification — 7 November 2026

The GPU-disabled ROS build passed all seven CTest entries, including the new
conversion and synthetic ROS publication/subscription tests. The 12 existing
Ouster Python tests passed. The conversion tests also passed AddressSanitizer
and UndefinedBehaviorSanitizer; leak detection was disabled because LeakSanitizer
cannot run under this environment's ptrace setup. The installed launch file's
arguments were checked, and a bounded launch selected signal / 65535 correctly
and shut down cleanly on SIGINT. This environment denied UDP socket/interface
operations during that launch: the synthetic ROS test runs within one process
and does not establish cross-process/host transport. Physical sensor reception,
the host's Zenoh setup, GPU inference and detection accuracy remain unverified.
No Docker image was rebuilt or deployed by these checks.

The combined launcher is checked separately with mocked Docker calls and real
local supervisor processes: source/divisor routing, custom settings, refusal of
conflicting containers and old images, Ctrl+C, failures of either process, and
cleanup of their descendants. These checks do not establish Docker/GPU or live
sensor operation of the combined pipeline.

## Recorded-bag conversion validation — 7 November 2026

Both original pinned Ouster OS1-32 bags were read directly, without network
playback or Docker. The actual C++ `ouster_to_xyzi` function and the detector's
actual `pack_xyzi` function processed every scan. Each bag database matched its
pinned SHA-256 before the test and remained unchanged afterward.

| Case | First bag | Second bag | Result |
| --- | ---: | ---: | --- |
| Recorded UINT16 reflectivity / 255 | 291 | 265 | Passed |
| Recorded FLOAT32 intensity explicitly mapped to `signal`, / 65535 | 291 | 265 | Passed |
| Reconstructed live-layout UINT8 reflectivity / 255 | 291 | 265 | Passed |
| Reconstructed live-layout UINT16 signal / 65535 | 291 | 265 | Passed |

That is 556 original scans, each with 32768 entries, tested in four cases
(2224 frame/case checks). All outputs preserved headers, organization, point order
and XYZ bytes. Every output intensity matched an independent numeric conversion
bit-for-bit, and the existing detector input packer accepted the outputs with the
expected finite point count. Full results and source/code hashes are recorded in
[`config/ouster_adapter_bag_validation.json`](../config/ouster_adapter_bag_validation.json).

The original bags do not have the live driver's schema: their signal is named
`intensity`, and reflectivity is UINT16. The legacy signal test maps that field
name in memory explicitly. Additional in-memory fixtures reconstruct the
documented 48-byte live layout, numerically converting the signal to UINT16 and
reflectivity to UINT8 only after checking that every value fits exactly. Scan
dimensions remain those of the recordings; these fixtures are not recordings
from the physical 128-channel sensor. The source bags are never rewritten.

To repeat the offline validation with installed ROS development dependencies:

```bash
source /opt/ros/jazzy/setup.bash
cmake -S . -B .recovery/ouster-bag-check-build \
  -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=ON -DBUILD_TESTING=ON \
  -DPython3_EXECUTABLE=/usr/bin/python3
cmake --build .recovery/ouster-bag-check-build --target ouster_adapter_probe -j 2
python3 tools/check_ouster_adapter_bags.py \
  --probe .recovery/ouster-bag-check-build/ouster_adapter_probe \
  --output .recovery/verification/ouster-adapter-bags.json
```

The Python checker defaults to the prepared bags under
`.recovery/rosbags/ouster_calibration_v3`; use `--data-dir` for a different root
containing the same pinned source bags. It does not download files.

### Full container replay on a GPU host (not executed here)

Docker daemon access was denied and no NVIDIA devices were exposed in the test
environment. Consequently, the recorded-bag checks above do not verify the
combined launcher, cross-process/host transport, TensorRT inference, detection
quality or throughput. On the GPU host, with an updated image containing the
adapter, use an isolated domain and matching Fast DDS middleware for both the
combined launcher and the existing bag-player container.

Terminal 1:

```bash
sudo env PP_CONTAINER_NAME=pointpillars-ouster-test ROS_DOMAIN_ID=99 \
  RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  OUSTER_POINT_CLOUD_TOPIC=/ouster_test/raw POINT_CLOUD_TOPIC=/ouster_test/xyzi \
  DETECTIONS_TOPIC=/ouster_test/bbox bash tools/start_ouster.sh reflectivity
```

After the engine and detector are ready, terminal 2:

```bash
ROS_DOMAIN_ID=99 POINT_CLOUD_TOPIC=/ouster_test/raw \
  PP_OUSTER_CONTAINER=pointpillars-ouster-test-bag \
  PP_BAG_LOOP=0 PP_OUSTER_FEATURE=raw_signal bash tools/rosbag_ouster.sh
```

Here `raw_signal` tells the bag helper to replay the original cloud unchanged;
the adapter still selects **reflectivity**. The helper remaps `/points` onto the
adapter's raw input, rather than feeding the detector directly. Do not select
`signal` in this full replay recipe: the original bag names that field
`intensity`; only the offline fixture above explicitly maps it to `signal`.

Inspect the adapter and detector separately in terminal 3:

```bash
sudo docker exec pointpillars-ouster-test /entrypoint.sh \
  ros2 topic echo /ouster_adapter/stats --once
sudo docker exec pointpillars-ouster-test /entrypoint.sh \
  ros2 topic echo /ouster_test/bbox/stats --qos-durability transient_local --once
```

Adapter converted counts should rise without input rejections; inspect the
detector's processed, invalid-cloud and inference-error counters independently.
The historical model has known inference/accuracy issues, so successful conversion
does not establish successful inference on every scan. The best-effort adapter
subscription can also drop scans during timed playback; exact counts are checked
by the offline validator, not promised for real-time playback. Ctrl+C in terminal
1 stops the combined pipeline; the nonlooping player exits after the selected bag.
