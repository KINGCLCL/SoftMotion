from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from softmotion.character.model import CharacterRegion, CharacterSettings, PartMotion, Point
from softmotion.motion.effects import MotionSettings
from softmotion.imaging.scene import SceneSettings


@dataclass
class ProjectData:
    source: QImage
    source_name: str
    motion: MotionSettings
    scene: SceneSettings
    character: CharacterSettings


def _validate_scene(scene, source):
    if not (64 <= int(scene.width) <= 1920 and 64 <= int(scene.height) <= 1920):
        raise ValueError("工程画布尺寸无效。 Project canvas dimensions are invalid.")
    if scene.background_mode not in {"transparent", "solid", "image"}:
        raise ValueError("工程背景类型无效。 Project background type is invalid.")
    if scene.background_mode == "image" and scene.background_image.isNull():
        raise ValueError("工程缺少背景图片。 The project is missing its background image.")
    if scene.crop is not None:
        if len(scene.crop) != 4:
            raise ValueError("工程裁剪数据无效。 Project crop data is invalid.")
        x, y, width, height = (int(value) for value in scene.crop)
        if x < 0 or y < 0 or width < 1 or height < 1 or x + width > source.width() or y + height > source.height():
            raise ValueError("工程裁剪区域超出图片范围。 Project crop area exceeds the image bounds.")


def _png_bytes(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("无法编码工程图片。 Could not encode a project image.")
    return bytes(buffer.data())


def _mask_image(mask):
    mask = np.ascontiguousarray(np.asarray(mask, dtype=np.uint8))
    image = QImage(mask.data, mask.shape[1], mask.shape[0], mask.strides[0], QImage.Format.Format_Grayscale8)
    return image.copy()


def _read_mask(data, shape):
    image = QImage.fromData(data).convertToFormat(QImage.Format.Format_Grayscale8)
    if image.isNull() or (image.width(), image.height()) != (shape[1], shape[0]):
        raise ValueError("工程蒙版尺寸无效。 Project mask dimensions are invalid.")
    rows = np.frombuffer(bytes(image.constBits()), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width()].copy()


def save_project(path, source, source_name, motion, scene, character):
    """Write a self-contained project and publish it atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    character = character.snapshot()
    scene = scene.snapshot()
    motion = MotionSettings(**asdict(motion))
    width, height = source.width(), source.height()
    character.validate(width, height)
    _validate_scene(scene, source)
    manifest = {
        "schema_version": 1,
        "working_size": [width, height],
        "source": "source.png",
        "source_name": str(source_name),
        "motion": asdict(motion),
        "scene": scene.metadata(),
        "character": character.metadata(),
    }
    for region, entry in zip(character.regions, manifest["character"]["regions"]):
        entry["mask"] = f"masks/region_{region.id}.png"
    if character.protection_mask is not None:
        manifest["character"]["protection_mask"] = "protection.png"
    if not scene.background_image.isNull():
        manifest["scene"]["background_image"] = "background.png"

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".softmotion-project-", suffix=".tmp", dir=path.parent,
                                         delete=False) as handle:
            temp_name = handle.name
        with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr("source.png", _png_bytes(source))
            if not scene.background_image.isNull():
                archive.writestr("background.png", _png_bytes(scene.background_image))
            for region in character.regions:
                archive.writestr(f"masks/region_{region.id}.png", _png_bytes(_mask_image(region.selection_mask)))
            if character.protection_mask is not None:
                archive.writestr("protection.png", _png_bytes(_mask_image(character.protection_mask)))
        os.replace(temp_name, path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
    return path


def _motion_from_dict(data):
    fields = set(MotionSettings.__dataclass_fields__)
    return MotionSettings(**{key: value for key, value in data.items() if key in fields})


def load_project(path):
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = json.loads(archive.read("project.json").decode("utf-8"))
            if manifest.get("schema_version") != 1:
                raise ValueError("不支持的工程版本。 Unsupported project version.")
            source = QImage.fromData(archive.read(manifest.get("source", "source.png"))).convertToFormat(QImage.Format.Format_RGBA8888)
            if source.isNull():
                raise ValueError("工程源图片无效。 The project source image is invalid.")
            width, height = manifest.get("working_size", [])
            if (source.width(), source.height()) != (width, height):
                raise ValueError("工程源图片尺寸不一致。 Project source dimensions do not match the manifest.")
            scene_data = manifest.get("scene", {})
            background = QImage()
            if scene_data.get("background_image"):
                background = QImage.fromData(archive.read(scene_data["background_image"])).convertToFormat(QImage.Format.Format_RGBA8888)
                if background.isNull():
                    raise ValueError("工程背景图片无效。 The project background image is invalid.")
            crop_data = scene_data.get("crop")
            crop = tuple(int(value) for value in crop_data) if crop_data is not None else None
            scene = SceneSettings(
                int(scene_data.get("width", 768)), int(scene_data.get("height", 768)),
                scene_data.get("background", "transparent"), scene_data.get("color", "#12151c"),
                background, crop,
            )
            _validate_scene(scene, source)
            character_data = manifest.get("character", {})
            shape = (height, width)
            regions = []
            for entry in character_data.get("regions", []):
                mask = _read_mask(archive.read(entry["mask"]), shape)
                motion = PartMotion(**{key: value for key, value in entry.get("motion", {}).items()
                                      if key in PartMotion.__dataclass_fields__})
                regions.append(CharacterRegion(
                    id=str(entry["id"]), name=str(entry.get("name", "部位")),
                    kind=entry.get("kind", "hair"), enabled=bool(entry.get("enabled", True)),
                    selection_mask=mask,
                    root=Point(*entry.get("root", [0, 0])), tip=Point(*entry.get("tip", [1, 1])),
                    root_lock_percent=float(entry.get("root_lock_percent", 12)),
                    feather_percent=float(entry.get("feather_percent", 8)), motion=motion,
                ))
            protection = None
            if character_data.get("protection_mask"):
                protection = _read_mask(archive.read(character_data["protection_mask"]), shape)
            character = CharacterSettings(bool(character_data.get("enabled", True)), regions, protection,
                                          int(character_data.get("revision", 0)))
            character.validate(width, height)
            return ProjectData(source, manifest.get("source_name", path.stem),
                               _motion_from_dict(manifest.get("motion", {})), scene, character)
    except (KeyError, IndexError, TypeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(("不支持", "工程", "工程蒙版")):
            raise
        raise ValueError(f"无法读取工程文件。 Could not read the project file: {exc}") from exc
