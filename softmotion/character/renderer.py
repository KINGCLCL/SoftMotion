import numpy as np
from math import ceil, radians

from softmotion.character.fields import _coordinates, region_field, static_geometry
from softmotion.character.masks import soft_mask
from softmotion.character.model import CharacterSettings
from softmotion.character.warp import qimage_to_rgba, rgba_to_qimage, warp_rgba


class CharacterRenderer:
    def __init__(self, source_image=None, settings=None):
        self.source_image = None
        self.settings = CharacterSettings()
        self.prepared_regions = []
        self.protection_weight = None
        self.coordinates = None
        self.bbox = None
        self.prepare(source_image, settings or CharacterSettings())

    def prepare(self, source_image, settings):
        self.source_image = source_image.copy() if source_image is not None else None
        self.settings = settings.snapshot()
        self.prepared_regions = []
        self.protection_weight = None
        self.bbox = None
        self.coordinates = None
        if self.source_image is None or self.source_image.isNull():
            return
        shape = (self.source_image.height(), self.source_image.width())
        self.settings.validate(self.source_image.width(), self.source_image.height())
        if self.settings.protection_mask is not None:
            self.protection_weight = soft_mask(self.settings.protection_mask, 3.0)
        boxes = []
        for region in self.settings.regions:
            if not region.enabled:
                continue
            if region.selection_mask.shape != shape:
                continue
            selection = soft_mask(region.selection_mask, region.feather_percent)
            self.prepared_regions.append((region, selection, None))
            rows, columns = np.nonzero(selection > 1e-4)
            if rows.size:
                length = max(1.0, float(np.hypot(region.tip.x - region.root.x, region.tip.y - region.root.y)))
                motion = region.motion
                radius = float(np.hypot(columns - region.root.x, rows - region.root.y).max())
                # Accessory rotation and torso width movement depend on the
                # selected pixels' distance from the root, which can be wider
                # than the root-to-tip guide.
                reach = length * abs(motion.amplitude_percent) / 100.0
                if region.kind == "accessory":
                    reach = max(reach, radius * abs(radians(motion.angle_degrees)))
                elif region.kind == "torso":
                    reach = max(reach, radius * abs(motion.width_ratio) * abs(motion.amplitude_percent) / 100.0)
                margin = ceil(max(4.0, reach))
                boxes.append((max(0, int(columns.min()) - margin), max(0, int(rows.min()) - margin),
                              min(shape[1], int(columns.max()) + margin + 1),
                              min(shape[0], int(rows.max()) + margin + 1)))
        if boxes:
            self.bbox = (min(box[0] for box in boxes), min(box[1] for box in boxes),
                         max(box[2] for box in boxes), max(box[3] for box in boxes))
            y0, x0 = self.bbox[1], self.bbox[0]
            y1, x1 = self.bbox[3], self.bbox[2]
            self.coordinates = _coordinates((y1 - y0, x1 - x0))
            self.coordinates = (self.coordinates[0] + x0, self.coordinates[1] + y0)
            self.prepared_regions = [
                (region, selection, static_geometry(region, self.coordinates))
                for region, selection, _ in self.prepared_regions
            ]
            self.prepared_regions = [
                (region, selection[y0:y1, x0:x1].copy(), geometry)
                for region, selection, geometry in self.prepared_regions
            ]
            if self.protection_weight is not None:
                self.protection_weight = self.protection_weight[y0:y1, x0:x1].copy()

    def render(self, image=None, phase=0.0):
        if image is None:
            image = self.source_image
        if image is None or image.isNull() or not self.settings.enabled or not self.prepared_regions or self.bbox is None:
            return image.copy() if image is not None else image
        if self.source_image is None:
            self.prepare(image, self.settings)
            if not self.prepared_regions or self.bbox is None:
                return image.copy()
        elif image.size() != self.source_image.size():
            raise ValueError("人物部位渲染器与图片尺寸不一致。 Character renderer and image dimensions do not match.")
        source = qimage_to_rgba(image)
        x0, y0, x1, y1 = self.bbox
        height, width = y1 - y0, x1 - x0
        displacement_x = np.zeros((height, width), dtype=np.float32)
        displacement_y = np.zeros((height, width), dtype=np.float32)
        total_weight = np.zeros((height, width), dtype=np.float32)
        for region, selection_weight, geometry in self.prepared_regions:
            dx, dy, weight = region_field(region, phase, (height, width), selection_weight,
                                          self.protection_weight, self.coordinates, geometry)
            displacement_x += dx * weight
            displacement_y += dy * weight
            total_weight += weight
        valid = total_weight > 1e-6
        displacement_x[valid] /= total_weight[valid]
        displacement_y[valid] /= total_weight[valid]
        displacement_x[~valid] = 0
        displacement_y[~valid] = 0
        output = source.copy()
        output[y0:y1, x0:x1] = warp_rgba(source[y0:y1, x0:x1], displacement_x, displacement_y)
        return rgba_to_qimage(output)


class PreviewCharacterRenderer:
    """Bound preview work independently of source size; exports use CharacterRenderer."""

    def __init__(self, long_edge=512):
        self.long_edge = long_edge
        self.renderer = CharacterRenderer()
        self.image = None
        self.cached = None
        self.cache_phase = None

    def prepare(self, image, settings):
        from dataclasses import replace
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from softmotion.character.model import Point
        self.cached = None
        self.cache_phase = None
        if image.isNull():
            self.image = image
            self.renderer.prepare(image, CharacterSettings())
            return
        self.image = image.scaled(self.long_edge, self.long_edge, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation) if max(image.width(), image.height()) > self.long_edge else image
        sx, sy = self.image.width() / image.width(), self.image.height() / image.height()

        def resize_mask(mask):
            if mask is None:
                return None
            mask = np.ascontiguousarray(mask)
            qmask = QImage(mask.data, mask.shape[1], mask.shape[0], mask.strides[0], QImage.Format.Format_Grayscale8)
            small = qmask.scaled(self.image.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            return np.frombuffer(small.constBits(), np.uint8).reshape(small.height(), small.bytesPerLine())[:, :small.width()].copy()

        regions = [replace(r, selection_mask=resize_mask(r.selection_mask),
                           root=Point(r.root.x * sx, r.root.y * sy),
                           tip=Point(r.tip.x * sx, r.tip.y * sy)) for r in settings.regions]
        self.renderer.prepare(self.image, replace(settings, regions=regions,
                                                  protection_mask=resize_mask(settings.protection_mask)))

    def render(self, image, phase=0.0):
        from PySide6.QtCore import Qt
        if self.cached is None or self.cache_phase != phase:
            result = self.renderer.render(self.image, phase)
            self.cached = result.scaled(image.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation) if result.size() != image.size() else result
            self.cache_phase = phase
        return self.cached
