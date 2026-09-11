import numpy as np


def normalize_mask(mask, shape):
    if mask is None:
        return np.zeros(shape, dtype=np.uint8)
    array = np.asarray(mask, dtype=np.uint8)
    if array.shape != tuple(shape):
        raise ValueError("部位蒙版尺寸与图片不一致。 Region mask size does not match the image.")
    return array


def paint_circle(mask, center, radius, value=255):
    """Paint a filled circle with a vectorized bounding-box operation."""
    height, width = mask.shape
    cx, cy = center
    left, right = max(0, int(cx - radius)), min(width, int(cx + radius + 1))
    top, bottom = max(0, int(cy - radius)), min(height, int(cy + radius + 1))
    if left >= right or top >= bottom:
        return
    yy, xx = np.ogrid[top:bottom, left:right]
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    mask[top:bottom, left:right][inside] = np.uint8(value)


def paint_line(mask, start, end, radius, value=255):
    length = max(1, int(np.hypot(end[0] - start[0], end[1] - start[1]) / max(1, radius * 0.45)))
    for point in zip(np.linspace(start[0], end[0], length), np.linspace(start[1], end[1], length)):
        paint_circle(mask, point, radius, value)


def box_blur(mask, radius):
    """Fast separable blur used to soften selection boundaries."""
    radius = int(radius)
    if radius <= 0:
        return np.asarray(mask, dtype=np.float32) / 255.0
    source = np.asarray(mask, dtype=np.float32)
    width = radius * 2 + 1
    padded = np.pad(source, ((0, 0), (radius, radius)), mode="edge")
    cumsum = np.cumsum(np.pad(padded, ((0, 0), (1, 0))), axis=1, dtype=np.float32)
    horizontal = (cumsum[:, width:] - cumsum[:, :-width]) / width
    padded = np.pad(horizontal, ((radius, radius), (0, 0)), mode="edge")
    cumsum = np.cumsum(np.pad(padded, ((1, 0), (0, 0))), axis=0, dtype=np.float32)
    blurred = (cumsum[width:] - cumsum[:-width]) / width
    return np.clip(blurred / 255.0, 0.0, 1.0)


def soft_mask(mask, feather_percent):
    mask = np.asarray(mask, dtype=np.uint8)
    short_edge = min(mask.shape) if mask.ndim == 2 else 1
    radius = max(0, round(short_edge * max(0.0, feather_percent) / 100.0))
    if radius == 0:
        return mask.astype(np.float32) / 255.0
    # Blend the original coverage with a blurred boundary so interiors remain solid.
    blurred = box_blur(mask, radius)
    original = mask.astype(np.float32) / 255.0
    return np.maximum(blurred * (original > 0), blurred * 0.35)
