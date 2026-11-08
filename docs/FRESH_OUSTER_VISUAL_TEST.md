# Fresh, unchanged Ouster recording: live GPU and RViz test

On 7 November 2026, a new download of the different MOSEP dataset was used for
an actual GPU/RViz test. Earlier sandbox-only tests did not have Docker/GPU
access; an approved host execution outside that sandbox provided access to
Docker, the RTX 4060 Laptop GPU and the desktop. No original dataset file was
modified or rewritten for this test.

## Fresh source and integrity

- Publisher: Gaisberger and Schlager, University of Graz / Virtual Vehicle
  Research, [MOSEP DigiTrans dataset](https://zenodo.org/records/19353314),
  DOI 10.5281/zenodo.19353314.
- Download: publisher's `digitrans_data.zip`, 963458462 bytes.
- Publisher MD5, verified after download: `574708d047bedf4b6263c24b7ae977f0`.
- Fresh folder: `.recovery/rosbags/ouster_mosep_fresh_20261107/`.
- Extracted publisher originals: `original/`, with all nine source files made
  read-only. Their SHA-256 hashes were rechecked after playback and unchanged.
- No reuse of the previous Koide bags or derived feature bags; no test fixtures,
  field renaming, numeric recoding or rewritten bag was used as the input.

The archive contains dry, 30 mm/h and 100 mm/h recordings from an Ouster
OS1-64-U02. The **dry** recording was played. Its first inspected LiDAR cloud
has 64 x 1024 entries, point_step 48 and frame `lidar/os_lidar`. The raw topic is
`/sensing/lidar/points`. Recorded fields are FLOAT32 XYZ/intensity, UINT32 t/range,
and UINT16 reflectivity/ring/ambient. The publisher's MCAP filenames contain
`converted`; those names are part of the downloaded source, not conversions
performed by this project.

## Executed pipeline

```text
Publisher's original MCAP (read-only bind mount, half-speed loop)
  -> /sensing/lidar/points (unchanged message payload)
  -> Ouster adapter: reflectivity / 255 -> FLOAT32 XYZI
  -> /ouster_fresh/xyzi
  -> GPU PointPillars (FP32, TensorRT 10.16.1, confidence 0.4)
  -> /ouster_fresh/bbox, /ouster_fresh/bbox/stats, /ouster_fresh/bbox/count
  -> RViz on the desktop
```

The recorded `intensity` field is present and remains untouched on the raw topic.
For this explicit adapter test, the selected fourth model feature is derived
from reflectivity during playback. It changes only the new output message.

`tools/start_ouster.sh` was used to run the combined adapter/detector container.
The saved `pp-infer:jazzy-trt10` image lacked the new adapter. A separate
`pp-infer:ouster-fresh-test` image was built from that saved image, compiling the
current adapter against the image's ROS libraries. Its detector, ONNX and
original saved image were preserved. Adapter source hashes are retained in
the test image and validation inventory. A 512 MiB workspace FP32 engine was
built successfully on the RTX 4060 and saved in the normal engine volume.

## Verified observations

The read-only ROS observer verified **40 raw/adapted pairs**: identical header,
dimensions, point order and XYZ bytes; FLOAT32 intensity equal bit-for-bit to an
independent reflectivity / 255 computation. It also matched **39 detection-array
headers** to those pairs. Its sampled adapter counters reported zero rejections.

A later detector snapshot reported **103 processed frames**, **29 cumulative
published detections**, **zero invalid-cloud frames** and **zero inference-error
frames**. These are snapshots of a continuing loop, not a claim of exact complete
bag delivery. Best-effort input and independent observer discovery can affect
observed counts.

RViz was opened on the desktop and visually inspected. The adapted point cloud
renders and the detection display reports OK; the capture shows a published-box
count. The fixed frame is the actual `lidar/os_lidar`. The original cloud is
available through the **Original Ouster cloud (toggle to compare)** display. A
global TF warning can remain because this replay selects the LiDAR topic rather
than a complete transform tree. The point cloud and boxes share the verified
sensor frame. A complete source-file SHA-256 recheck after playback passed.

This verifies live adapter/transport/GPU/publication/RViz integration.
**Detection accuracy and model feature calibration remain unvalidated.** A
published box is not a ground-truth match, and some scans publish no boxes after
the 0.4 confidence gate.

Detailed source hashes, adapter build provenance and live results are in
[`config/ouster_fresh_visual_validation.json`](../config/ouster_fresh_visual_validation.json).
Local logs, source manifest, observer and screenshot are under
`.recovery/ouster-fresh-test/` and the fresh download folder. These ignored
artifacts need an independent backup if they must be retained.

## Restart the same visual test

For the current default scripts, see [startup and replay](STARTUP_AND_REPLAY.md).
The commands below also preserve the original 7 November isolated-image setup;
the bag helper below explicitly selects the same test image.
Do not start duplicates while these test processes are running. Terminal 1,
from the checkout:

```bash
PP_IMAGE=pp-infer:ouster-fresh-test PP_CONTAINER_NAME=pointpillars-ouster-fresh \
  ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  OUSTER_POINT_CLOUD_TOPIC=/sensing/lidar/points \
  POINT_CLOUD_TOPIC=/ouster_fresh/xyzi DETECTIONS_TOPIC=/ouster_fresh/bbox \
  bash tools/start_ouster.sh reflectivity
```

Terminal 2 (the helper starts only the unchanged bag player):

```bash
PP_IMAGE=pp-infer:ouster-fresh-test bash tools/start_ouster_bag.sh
```

It defaults to the dry recording, half-speed loop, Fast DDS, domain 99 and the
saved `pp-infer:jazzy-trt10` image (updated 8 November). Use `rain30` or `rain100` to select
another downloaded recording. Set `PP_BAG_LOOP=0` for a single pass, and see
`bash tools/start_ouster_bag.sh --help` for source directory, topic, domain and
image overrides. An existing player is preserved and reported rather than
restarted. The equivalent direct Docker command is:

```bash
docker run --pull=never --rm --init --name pointpillars-ouster-fresh-bag \
  --network host --ipc host -e ROS_DOMAIN_ID=99 \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp -e FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
  --mount "type=bind,source=$PWD/.recovery/rosbags/ouster_mosep_fresh_20261107/original/digitrans_40kmh_dry,target=/bag,readonly" \
  pp-infer:ouster-fresh-test ros2 bag play /bag \
  --topics /sensing/lidar/points --rate 0.5 --loop --delay 3 \
  --disable-keyboard-controls
```

Terminal 3, on the graphical desktop:

```bash
ROS_DOMAIN_ID=99 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  RVIZ_CONFIG="$PWD/.recovery/ouster-fresh-test/rviz-ouster-fresh.rviz" \
  bash tools/visualize.sh
```

Docker commands above require Docker access; use sudo on a host that requires it.
To stop just these test containers:

```bash
docker stop pointpillars-ouster-fresh-bag pointpillars-ouster-fresh
```

Close the test RViz window normally. The downloaded bags, saved images and engine
cache remain available.
