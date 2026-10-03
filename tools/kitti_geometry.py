"""KITTI ground truth in rectified-camera and LiDAR coordinates (standard library)."""
import math
import struct
import zlib

TYPES = {'Car', 'Van', 'Truck', 'Pedestrian', 'Person_sitting', 'Cyclist', 'Tram', 'Misc', 'DontCare'}


def matmul(a, b):
    return [[sum(x * y for x, y in zip(row, col)) for col in zip(*b)] for row in a]


def matvec(a, v):
    return [sum(x * y for x, y in zip(row, v)) for row in a]


def transpose(a):
    return [list(row) for row in zip(*a)]


def inverse3(a):
    augmented = [list(row) + [float(i == j) for j in range(3)] for i, row in enumerate(a)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda i: abs(augmented[i][col]))
        if abs(augmented[pivot][col]) < 1e-10:
            raise ValueError('Singular calibration rotation')
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        scale = augmented[col][col]
        augmented[col] = [x / scale for x in augmented[col]]
        for row in range(3):
            if row != col:
                factor = augmented[row][col]
                augmented[row] = [x - factor * y for x, y in zip(augmented[row], augmented[col])]
    return [row[3:] for row in augmented]


def check_rotation(r):
    product = matmul(r, transpose(r))
    det = (r[0][0] * (r[1][1]*r[2][2]-r[1][2]*r[2][1])
           - r[0][1] * (r[1][0]*r[2][2]-r[1][2]*r[2][0])
           + r[0][2] * (r[1][0]*r[2][1]-r[1][1]*r[2][0]))
    if max(abs(product[i][j] - float(i == j)) for i in range(3) for j in range(3)) > 1e-4 or abs(det - 1) > 1e-4:
        raise ValueError('Calibration rotation must be proper and orthonormal')


class Calibration:
    def __init__(self, text):
        entries = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            key, values = line.split(':', 1)
            if key in entries:
                raise ValueError('Duplicate calibration key: ' + key)
            entries[key] = [float(x) for x in values.split()]
            if not all(math.isfinite(x) for x in entries[key]):
                raise ValueError('Nonfinite calibration value')
        for key, size in [('P2', 12), ('R0_rect', 9), ('Tr_velo_to_cam', 12)]:
            if key not in entries or len(entries[key]) != size:
                raise ValueError('Missing or invalid calibration matrix: ' + key)
        rect = [entries['R0_rect'][i:i+3] for i in (0, 3, 6)]
        extrinsic = [entries['Tr_velo_to_cam'][i:i+4] for i in (0, 4, 8)]
        rotation = [row[:3] for row in extrinsic]
        check_rotation(rect)
        check_rotation(rotation)
        self.rotation = matmul(rect, rotation)
        self.translation = matvec(rect, [row[3] for row in extrinsic])
        # Invert the actual rounded calibration, not an assumed exact transpose.
        self.inverse_rotation = inverse3(self.rotation)
        self.projection = [entries['P2'][i:i+4] for i in (0, 4, 8)]

    def to_camera(self, point):
        return [x + y for x, y in zip(matvec(self.rotation, point), self.translation)]

    def to_lidar(self, point):
        return matvec(self.inverse_rotation, [x - y for x, y in zip(point, self.translation)])

    def project_camera(self, point):
        q = matvec(self.projection, list(point) + [1])
        if point[2] <= 0 or q[2] <= 0:
            return None
        return [q[0] / q[2], q[1] / q[2]]


def parse_labels(text):
    labels = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 15 or fields[0] not in TYPES:
            raise ValueError(f'Invalid ground-truth label at line {number}; expected type plus 14 values')
        values = [float(x) for x in fields[1:]]
        if not all(math.isfinite(x) for x in values):
            raise ValueError('Nonfinite label value')
        trunc, occ, alpha = values[:3]
        bbox, dimensions, bottom, yaw = values[3:7], values[7:10], values[10:13], values[13]
        if bbox[2] < bbox[0] or bbox[3] < bbox[1]:
            raise ValueError('Inverted image bounding box')
        if fields[0] != 'DontCare':
            if not 0 <= trunc <= 1 or occ not in (0, 1, 2, 3) or min(dimensions) <= 0 or abs(yaw) > math.pi + .01:
                raise ValueError('Invalid object truncation/occlusion/dimensions/yaw')
        labels.append({'type': fields[0], 'truncated': trunc, 'occluded': int(occ),
                       'alpha': alpha, 'bbox_image': bbox, 'dimensions_hwl': dimensions,
                       'bottom_center_camera': bottom, 'rotation_y': yaw})
    return labels


def difficulty(label):
    """Metadata buckets only; this is not the official KITTI evaluator."""
    if label['type'] == 'DontCare':
        return 'ignore'
    height = label['bbox_image'][3] - label['bbox_image'][1]
    for name, min_height, max_occ, max_trunc in [('easy', 40, 0, .15), ('moderate', 25, 1, .3), ('hard', 25, 2, .5)]:
        if height >= min_height and label['occluded'] <= max_occ and label['truncated'] <= max_trunc:
            return name
    return 'outside_difficulty'


def convert_box(label, calibration, spatial_range):
    if label['type'] == 'DontCare':
        return None  # Keep original image ignore region, never invent a 3D box.
    h, w, length = label['dimensions_hwl']
    center_camera = list(label['bottom_center_camera'])
    center_camera[1] -= h / 2
    center = calibration.to_lidar(center_camera)
    c, s = math.cos(label['rotation_y']), math.sin(label['rotation_y'])
    camera_rotation = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    # Local x along length, y along width, z upward; proper right-handed frame.
    local_to_camera = matmul(camera_rotation, [[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    orientation = matmul(calibration.inverse_rotation, local_to_camera)
    dims = [length, w, h]
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                offset = matvec(orientation, [sx*length/2, sy*w/2, sz*h/2])
                corners.append([x + y for x, y in zip(center, offset)])
    inside = lambda p: all(spatial_range[i] <= p[i] < spatial_range[i+3] for i in range(3))
    heading = [row[0] for row in orientation]
    return {'center_lidar': center, 'dimensions_lwh': dims, 'orientation_lidar': orientation,
            'corners_lidar': corners, 'heading_lidar': heading,
            'yaw_lidar_diagnostic': math.atan2(heading[1], heading[0]),
            'difficulty_bucket': difficulty(label), 'center_in_model_range': inside(center),
            'all_corners_in_model_range': all(inside(p) for p in corners),
            'projected_corners': [calibration.project_camera(calibration.to_camera(p)) for p in corners]}


def inspect_cloud(data, spatial_range, capacity):
    if not data or len(data) % 16:
        raise ValueError('Point cloud must contain complete little-endian float32 XYZI points')
    count, inside, nonfinite, intensity_outside = len(data)//16, 0, 0, 0
    low, high = math.inf, -math.inf
    for point in struct.iter_unpack('<ffff', data):
        if not all(math.isfinite(x) for x in point):
            nonfinite += 1
            continue
        low, high = min(low, point[3]), max(high, point[3])
        intensity_outside += int(not 0 <= point[3] <= 1)
        inside += int(all(spatial_range[i] <= point[i] < spatial_range[i+3] for i in range(3)))
    return {'points': count, 'nonfinite_points': nonfinite, 'finite_points_in_model_range': inside,
            'intensity_min': low if low != math.inf else None,
            'intensity_max': high if high != -math.inf else None,
            'intensity_outside_0_1': intensity_outside, 'exceeds_engine_capacity': count > capacity}


def png_dimensions(data):
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[8:16] != b'\x00\x00\x00\rIHDR':
        raise ValueError('Invalid PNG header')
    if zlib.crc32(data[12:29]) & 0xffffffff != struct.unpack('>I', data[29:33])[0]:
        raise ValueError('Invalid PNG IHDR checksum')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height:
        raise ValueError('Invalid image dimensions')
    return [width, height]
