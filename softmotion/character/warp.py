import numpy as np
from PySide6.QtGui import QImage


def qimage_to_rgba(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(bytes(image.constBits()), dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)[:, :image.width()].copy()


def rgba_to_qimage(array):
    array = np.ascontiguousarray(np.clip(array, 0, 255).astype(np.uint8))
    image = QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format.Format_RGBA8888)
    return image.copy()


def warp_rgba(source, displacement_x, displacement_y):
    """Inverse bilinear sampling with premultiplied RGB to avoid transparent halos."""
    height, width = source.shape[:2]
    if not np.any(displacement_x) and not np.any(displacement_y):
        return source.copy()
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    sample_x, sample_y = xx - displacement_x, yy - displacement_y
    x0, y0 = np.floor(sample_x).astype(np.int32), np.floor(sample_y).astype(np.int32)
    fx, fy = sample_x - x0, sample_y - y0
    output = np.zeros_like(source)
    premultiplied = source[:, :, :3].astype(np.float32) * (source[:, :, 3:4].astype(np.float32) / 255.0)
    alpha = source[:, :, 3].astype(np.float32)
    accum_rgb = np.zeros((height, width, 3), dtype=np.float32)
    accum_alpha = np.zeros((height, width), dtype=np.float32)
    for ox, oy, weight in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                            (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        sx, sy = x0 + ox, y0 + oy
        valid = (sx >= 0) & (sx < width) & (sy >= 0) & (sy < height)
        safe_x, safe_y = np.clip(sx, 0, width - 1), np.clip(sy, 0, height - 1)
        sample_weight = weight * valid
        accum_rgb += premultiplied[safe_y, safe_x] * sample_weight[:, :, None]
        accum_alpha += alpha[safe_y, safe_x] * sample_weight
    output[:, :, 3] = np.clip(accum_alpha, 0, 255).astype(np.uint8)
    visible = accum_alpha > 1e-5
    output[:, :, :3][visible] = np.clip(accum_rgb[visible] * 255.0 / accum_alpha[visible, None], 0, 255).astype(np.uint8)
    return output
