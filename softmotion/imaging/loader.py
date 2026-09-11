from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtGui import QImage


@dataclass(frozen=True)
class LoadedImage:
    path: Path
    width: int
    height: int
    preview: QImage


def load_image(path: str | Path) -> LoadedImage:
    """Preserve transparency, correct orientation and cap preview memory usage."""
    path = Path(path)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("请选择 PNG、JPG 或 WebP 图片。 Please select a PNG, JPG, or WebP image.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("文件内容不是支持的图片格式。 The file contents are not a supported image format.")
                if getattr(source, "is_animated", False):
                    raise ValueError("V0.1 仅支持静态图片，请选择单帧图片。 V0.1 supports still images only. Select a single-frame image.")
                # Reject oversized assets before decoding; retain Pillow's bomb checks.
                if source.width * source.height > 40_000_000:
                    raise ValueError("图片超过 4000 万像素，请缩小后再导入。 The image exceeds 40 megapixels. Resize it before importing.")
                oriented = ImageOps.exif_transpose(source)
                width, height = oriented.size
                oriented.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                pixels = np.ascontiguousarray(oriented.convert("RGBA"), dtype=np.uint8)
                h, w, _ = pixels.shape
                preview = QImage(pixels.data, w, h, pixels.strides[0],
                                 QImage.Format.Format_RGBA8888).copy()
                return LoadedImage(path, width, height, preview)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError(f"无法读取图片 Cannot read image: {exc}") from exc
