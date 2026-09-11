from math import radians, sin, tau

import numpy as np


def _coordinates(shape):
    height, width = shape
    yy, xx = np.mgrid[0:height, 0:width]
    return xx.astype(np.float32), yy.astype(np.float32)


def static_geometry(region, coordinates):
    xx, yy = coordinates
    root_x, root_y = region.root.x, region.root.y
    axis_x, axis_y = region.tip.x - root_x, region.tip.y - root_y
    length = max(1.0, float(np.hypot(axis_x, axis_y)))
    direction_x, direction_y = axis_x / length, axis_y / length
    normal_x, normal_y = -direction_y, direction_x
    projection = np.clip(((xx - root_x) * direction_x + (yy - root_y) * direction_y) / length, 0.0, 1.0)
    lock = np.clip(region.root_lock_percent / 100.0, 0.0, 0.95)
    u = np.clip((projection - lock) / max(1e-6, 1.0 - lock), 0.0, 1.0)
    root_weight = u * u * (3.0 - 2.0 * u)
    return projection, root_weight, length, direction_x, direction_y, normal_x, normal_y


def region_field(region, phase, shape, selection_weight, protection_weight=None, coordinates=None, geometry=None):
    """Return dx, dy and effective weights for one region in source coordinates."""
    phase = phase % 1.0
    xx, yy = coordinates if coordinates is not None else _coordinates(shape)
    root_x, root_y = region.root.x, region.root.y
    if geometry is None:
        geometry = static_geometry(region, coordinates if coordinates is not None else _coordinates(shape))
    projection, root_weight, length, direction_x, direction_y, normal_x, normal_y = geometry
    weight = selection_weight * root_weight
    if protection_weight is not None:
        weight *= 1.0 - np.clip(protection_weight, 0.0, 1.0)

    motion = region.motion
    local_phase = motion.cycles * phase + motion.phase_offset
    if region.kind == "accessory":
        angle = radians(motion.angle_degrees) * sin(tau * local_phase)
        relative_x, relative_y = xx - root_x, yy - root_y
        rotated_x = np.cos(angle) * relative_x - np.sin(angle) * relative_y
        rotated_y = np.sin(angle) * relative_x + np.cos(angle) * relative_y
        displacement_x = (rotated_x - relative_x) * root_weight
        displacement_y = (rotated_y - relative_y) * root_weight
    elif region.kind == "torso":
        wave = sin(tau * local_phase)
        amplitude = length * motion.amplitude_percent / 100.0
        lateral_distance = (xx - root_x) * normal_x + (yy - root_y) * normal_y
        axial = amplitude * root_weight * wave
        lateral = lateral_distance * motion.width_ratio * motion.amplitude_percent / 100.0 * root_weight * wave
        displacement_x = direction_x * axial + normal_x * lateral
        displacement_y = direction_y * axial + normal_y * lateral
    else:
        theta = tau * (local_phase - motion.tip_lag * projection)
        amplitude = length * motion.amplitude_percent / 100.0
        wave = np.sin(theta)
        if region.kind == "cloth":
            wave = (wave + 0.15 * np.sin(2.0 * theta + 0.5)) / 1.15
        offset = amplitude * np.power(root_weight, max(0.1, motion.bend_power)) * wave
        displacement_x = normal_x * offset
        displacement_y = normal_y * offset
    return displacement_x.astype(np.float32), displacement_y.astype(np.float32), weight.astype(np.float32)
