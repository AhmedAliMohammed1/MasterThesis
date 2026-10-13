# Original LiDAR detail and a forward-camera KITTI comparison

This update addresses the sparse RViz scene and adds a different road recording. It does not change model weights, confidence thresholds, NMS or existing source recordings.

## Why the Ouster scene can look sparse

The Ouster bag has **32,768 entries per scan**. In the frozen feature experiment, **13,206–15,775 entries per scan had zero range and zero XYZ**. Those entries overlap at the sensor origin and do not describe additional scene surfaces. The original source itself is therefore much sparser than the earlier KITTI HDL-64E data. Coordinate hashes and byte comparisons show that feature normalization did not remove or move the remaining points.

The prior view also used two-pixel points and an orbit distance of 65 m; adding a camera panel can reduce the space available to the 3D scene. Its intensity colors followed the normalized model feature. These are display/feature effects, distinct from actual deletion of source points.

## Restored original-data view

The detail launcher adds `/ouster/raw_points`, containing **the original serialized cloud, including the original signal values and every auxiliary channel**. The detector still receives normalized `/point_cloud`. Both clouds keep their original coordinates, count, order and timestamps. Cameras are included. The separate view moves closer (28 m) and uses brighter three-pixel points so geometry is visible independently of feature values.

```bash
# Stop the current Ouster helper player before selecting the detail mode:
bash tools/rosbag_ouster.sh stop
bash tools/rosbag_ouster_detail.sh
# Another terminal:
RVIZ_CONFIG="$PWD/rviz/ouster_detail.rviz" bash tools/visualize.sh
```

The default **Original LiDAR geometry** display uses a light flat color. To inspect original return signal colors, disable that display and enable **Original signal colors (optional)**. Both use the original-data topic; the color limits are automatic, without clipping the source values. No new points are created, and zero-range entries are preserved. The second Ouster sequence remains selectable through `PP_OUSTER_SEQUENCE`.

The detail wrapper selects the previously tested `reflectivity_div255` inference candidate, `PP_OUSTER_RAW_VIEW=1` and camera playback. Its new bag is stored separately under `.recovery/rosbags/ouster_calibration_v3/raw_view/reflectivity_div255/<sequence>/`. Existing raw, derived and visual bags remain intact. The raw-view builder checks source hashes and copies serialized records; it does not recompute the cloud. Five matching live clouds passed byte comparisons of **every non-intensity byte** across original and normalized streams, including UINT8 ring values, padding, XYZ and auxiliary channels.

## New forward-facing recording

The new recording is official **KITTI raw synced drive `2011_09_26_drive_0005_sync`**, different from the previously used drive 0016/odometry sequence04. The front left color camera looks along the road: the inspected frames show an urban intersection, a van, a cyclist, pedestrians and buildings.

Source: [KITTI raw data](https://www.cvlibs.net/datasets/kitti/raw_data.php) and [sensor setup](https://www.cvlibs.net/datasets/kitti/setup.php). KITTI describes synced/rectified streams and the HDL-64E scan rate/camera triggering. Attribution: Andreas Geiger, Philip Lenz, Christoph Stiller and Raquel Urtasun; KIT/TTI-C. Dataset license: **CC-BY-NC-SA-3.0**, as stated on [the KITTI site](https://www.cvlibs.net/datasets/kitti/). Preserve attribution/license with redistributed derivatives.

| Property | Measured value |
| --- | --- |
| Download | 645,940,900-byte official drive ZIP plus 4,068-byte calibration ZIP |
| Clouds / front-camera images | 154 / 154 |
| Points per scan | 98,532–124,122; median 122,651 |
| Total finite source points | 18,746,749 |
| Zero-XYZ source points | 0 |
| Intensity range | 0–0.99, preserved without rescaling |
| Cloud timeline span | 15.7996 s |
| Camera resolution | 1242×375, preserved in ROS |
| Camera video | 15.900 s, 1242×376 (one padding row; no crop/downscale) |
| Image timestamp minus paired cloud timestamp | 9.99–10.61 ms, preserved |

**Forward-facing refers to the camera and the saved viewing direction. The full 360-degree LiDAR scan is retained.** No front-only point filter is added because the user requested more scene detail, and the model receives the original full XYZI input.

Default assets: `.recovery/rosbags/kitti_front_0005/`. The generated ROS 2 bag is `rosbag/`; the frontal MP4 is `camera/front_camera.mp4`; all original front PNGs and timestamps are retained. The official calibration files are under `calibration/`. Original archives are SHA256-pinned and all source member reads verify ZIP CRCs. OXTS and the other cameras remain in the untouched source archive but are not published by this focused comparison bag.

## Play and compare

Keep the detector running. Stop the current player before switching; simultaneous inputs on the same topic/domain make comparison ambiguous.

```bash
bash tools/rosbag_ouster.sh stop
bash tools/rosbag_kitti_front.sh
# Another terminal:
RVIZ_CONFIG="$PWD/rviz/kitti_front.rviz" bash tools/visualize.sh
```

The KITTI view uses fixed frame `velodyne`, bright points, a closer orbit looking forward along X, detection scores, and the front camera in a separate Image panel. The camera projection matrix is copied from official `P_rect_02` and identified in the common KITTI rectified reference frame. Source calibration is retained; no invented world TF or detection-image overlay is added.

Other commands:

```bash
bash tools/rosbag_kitti_front.sh prepare  # Reuse verified archive/bag/video.
bash tools/rosbag_kitti_front.sh info
bash tools/rosbag_kitti_front.sh stop
ROS_DOMAIN_ID=99 PP_BAG_LOOP=0 bash tools/rosbag_kitti_front.sh
```

Match the domain across inference, player and viewer. Default playback is half recorded speed, looping; native stream rate is approximately 10 Hz. The video plays at recorded speed independently of ROS; it is not automatically synchronized with a separate video player. Settings include `PP_KITTI_FRONT_DIR`, `PP_KITTI_FRONT_CONTAINER`, `PP_IMAGE`, `PP_BAG_RATE`, `PP_BAG_LOOP`, `PP_BAG_DURATION`, `PP_BAG_DELAY`, `POINT_CLOUD_TOPIC`; see `--help`.

## Checks and limits

The full new bag ran through the unchanged deployment engine on isolated domain 99: **154 source clouds, 154 matching detections, 154 camera images and 154 CameraInfo messages** were received. Every published cloud's XYZI hash matched its original `.bin`, and all 154 camera pixel arrays matched the decoded source PNGs exactly; no invalid message fields or detector log errors were recorded. Published detections ranged 83–132 per frame (median 106). These counts do not establish accuracy. Neither reviewed detection labels nor an accuracy pass are claimed for this new clip.

The raw Ouster view passed isolated live byte checks. Video codec/dimensions/timing checks passed, source and decoded frontal video frames were visually inspected, and existing inputs were retained. Focused projection/ownership tests and the Ouster input/feature/camera controls passed. The source archive, generated bag, native observations, helper hashes and visual-view settings are indexed by `config/kitti_front_inventory.json` and `config/ouster_detail_inventory.json`. Test players and the temporary KITTI detector were stopped; existing main-domain playback was retained. New saved RViz profiles were checked as configuration artifacts; actual desktop rendering of these new profiles is not claimed.
