"""Explicit diagnostic Ouster feature conversions; none is an accepted model calibration."""
import numpy as np

VARIANTS = {
    'raw_signal': 'Recorded FLOAT32 intensity (Ouster signal), unchanged',
    'signal_div65535': 'Signal / 65535; numeric-range control, not calibrated reflectance',
    'reflectivity_div255': 'Reflectivity code / 255; bounded encoding, not physical linear reflectance',
    'reflectivity_fraction': 'min(reflectivity / 100, 1); diffuse-target fraction with retroreflectors clipped',
}


def channel(msg, name):
    matches = [f for f in msg.fields if f.name == name]
    if len(matches) != 1 or matches[0].count != 1 or msg.is_bigendian:
        raise ValueError('Missing/ambiguous scalar little-endian field: ' + name)
    field = matches[0]
    dtype = {7: '<f4', 4: '<u2', 6: '<u4'}.get(field.datatype)
    if dtype is None or field.offset + np.dtype(dtype).itemsize > msg.point_step:
        raise ValueError('Unsupported field layout: ' + name)
    if len(msg.data) != msg.row_step * msg.height or msg.row_step < msg.width * msg.point_step:
        raise ValueError('Inconsistent cloud layout')
    return np.ndarray((msg.height, msg.width), dtype=dtype, buffer=msg.data,
                      offset=field.offset, strides=(msg.row_step, msg.point_step))


def feature_values(signal, reflectivity, variant):
    signal = np.asarray(signal, dtype='<f4')
    reflectivity = np.asarray(reflectivity)
    if signal.shape != reflectivity.shape or not np.isfinite(signal).all():
        raise ValueError('Invalid signal/reflectivity input')
    if variant == 'raw_signal':
        return signal.copy()
    if variant == 'signal_div65535':
        if np.any(signal < 0) or np.any(signal > 65535):
            raise ValueError('Signal exceeds the tested 16-bit control range')
        return signal / np.float32(65535)
    if variant not in ('reflectivity_div255', 'reflectivity_fraction'):
        raise ValueError('Unknown feature variant')
    if not np.isfinite(reflectivity).all() or np.any(reflectivity < 0) or np.any(reflectivity > 255):
        raise ValueError('Reflectivity does not fit the documented 8-bit code range')
    values = reflectivity.astype('<f4')
    if variant == 'reflectivity_div255':
        return values / np.float32(255)
    return np.minimum(values / np.float32(100), np.float32(1))


def packed_variant(msg, variant):
    result = np.empty((msg.width * msg.height, 4), dtype='<f4')
    for index, name in enumerate(('x', 'y', 'z')):
        values = channel(msg, name)
        if values.dtype != np.dtype('<f4') or not np.isfinite(values).all():
            raise ValueError('XYZ must be finite FLOAT32')
        result[:, index] = values.ravel()
    result[:, 3] = feature_values(channel(msg, 'intensity'), channel(msg, 'reflectivity'), variant).ravel()
    return result


def converted_message(msg, variant):
    """Copy the cloud, changing only bytes of its existing FLOAT32 intensity field."""
    from copy import deepcopy
    from array import array
    result = deepcopy(msg)
    field = next(f for f in result.fields if f.name == 'intensity')
    if field.datatype != 7:
        raise ValueError('Destination intensity must be FLOAT32')
    values = feature_values(channel(msg, 'intensity'), channel(msg, 'reflectivity'), variant)
    payload = bytearray(msg.data)
    target = np.ndarray((msg.height, msg.width), dtype='<f4', buffer=payload,
                        offset=field.offset, strides=(msg.row_step, msg.point_step))
    target[:] = values
    result.data = array('B', payload)
    return result
