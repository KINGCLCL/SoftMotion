from dataclasses import dataclass, field
from typing import Literal
import uuid

import numpy as np


PartKind = Literal["hair", "cloth", "accessory", "torso"]


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def as_tuple(self):
        return [float(self.x), float(self.y)]


@dataclass
class PartMotion:
    amplitude_percent: float = 3.0
    angle_degrees: float = 3.0
    cycles: int = 1
    phase_offset: float = 0.0
    tip_lag: float = 0.12
    bend_power: float = 1.8
    width_ratio: float = 0.15


def defaults_for_kind(kind):
    if kind == "cloth":
        return PartMotion(amplitude_percent=2.5, tip_lag=0.16, bend_power=1.4)
    if kind == "accessory":
        return PartMotion(amplitude_percent=0.0, angle_degrees=3.0, tip_lag=0.0, bend_power=1.0)
    if kind == "torso":
        return PartMotion(amplitude_percent=0.5, bend_power=1.0, width_ratio=0.15)
    return PartMotion()


@dataclass
class CharacterRegion:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "新部位"
    kind: PartKind = "hair"
    enabled: bool = True
    selection_mask: np.ndarray = field(default_factory=lambda: np.zeros((1, 1), dtype=np.uint8))
    root: Point = field(default_factory=lambda: Point(0, 0))
    tip: Point = field(default_factory=lambda: Point(1, 1))
    root_lock_percent: float = 12.0
    feather_percent: float = 8.0
    motion: PartMotion = field(default_factory=PartMotion)

    def snapshot(self):
        return CharacterRegion(
            self.id, self.name, self.kind, self.enabled, self.selection_mask.copy(),
            Point(self.root.x, self.root.y), Point(self.tip.x, self.tip.y),
            self.root_lock_percent, self.feather_percent,
            PartMotion(**vars(self.motion)),
        )


@dataclass
class CharacterSettings:
    enabled: bool = True
    regions: list[CharacterRegion] = field(default_factory=list)
    protection_mask: np.ndarray | None = None
    revision: int = 0

    def snapshot(self):
        return CharacterSettings(
            self.enabled,
            [region.snapshot() for region in self.regions],
            None if self.protection_mask is None else self.protection_mask.copy(),
            self.revision,
        )

    def bump(self):
        self.revision += 1

    def ensure_size(self, width, height):
        shape = (int(height), int(width))
        for region in self.regions:
            if region.selection_mask.shape != shape:
                region.selection_mask = np.zeros(shape, dtype=np.uint8)
        if self.protection_mask is not None and self.protection_mask.shape != shape:
            self.protection_mask = np.zeros(shape, dtype=np.uint8)

    def validate(self, width, height):
        shape = (int(height), int(width))
        valid_kinds = {"hair", "cloth", "accessory", "torso"}
        if self.protection_mask is not None and self.protection_mask.shape != shape:
            raise ValueError("保护蒙版尺寸与图片不一致。 Protection mask size does not match the image.")
        for region in self.regions:
            if region.kind not in valid_kinds or region.selection_mask.shape != shape:
                raise ValueError("人物部位数据无效。 Character region data is invalid.")
            if not all(np.isfinite(value) for value in (region.root.x, region.root.y, region.tip.x, region.tip.y)):
                raise ValueError("人物部位控制点无效。 Character control points are invalid.")
            if not all(0 <= value < limit for value, limit in (
                    (region.root.x, width), (region.root.y, height),
                    (region.tip.x, width), (region.tip.y, height))):
                raise ValueError("人物部位控制点超出图片范围。 Character control points are outside the image.")
            if float(np.hypot(region.tip.x - region.root.x, region.tip.y - region.root.y)) <= 1e-6:
                raise ValueError("人物部位根点与尖端不能重合。 Root and tip control points must be separated.")
            if not 1 <= int(region.motion.cycles) <= 4:
                raise ValueError("动作循环次数需要在 1–4 之间。 Motion cycles must be between 1 and 4.")
            motion = region.motion
            values = (motion.amplitude_percent, motion.angle_degrees, motion.phase_offset,
                      motion.tip_lag, motion.bend_power, motion.width_ratio,
                      region.root_lock_percent, region.feather_percent)
            if not all(np.isfinite(value) for value in values):
                raise ValueError("人物部位参数无效。 Character region parameters are invalid.")
            if not 0 <= motion.amplitude_percent <= 30 or not 0 <= motion.angle_degrees <= 20:
                raise ValueError("部位运动幅度超出范围。 Part motion amplitude is out of range.")
            if not 0 <= motion.phase_offset <= 1 or not 0 <= motion.tip_lag <= 0.35:
                raise ValueError("部位相位参数超出范围。 Part phase parameters are out of range.")
            if not 0.1 <= motion.bend_power <= 4 or not 0 <= motion.width_ratio <= 1:
                raise ValueError("部位形变参数超出范围。 Part deformation parameters are out of range.")
            if not 0 <= region.root_lock_percent <= 95 or not 0 <= region.feather_percent <= 30:
                raise ValueError("部位边界参数超出范围。 Part boundary parameters are out of range.")

    def metadata(self):
        return {
            "enabled": self.enabled,
            "revision": self.revision,
            "regions": [
                {
                    "id": region.id,
                    "name": region.name,
                    "kind": region.kind,
                    "enabled": region.enabled,
                    "root": region.root.as_tuple(),
                    "tip": region.tip.as_tuple(),
                    "root_lock_percent": region.root_lock_percent,
                    "feather_percent": region.feather_percent,
                    "motion": vars(region.motion).copy(),
                }
                for region in self.regions
            ],
            "has_protection": self.protection_mask is not None,
        }


def new_region(width, height, name="新部位", kind="hair"):
    return CharacterRegion(
        name=name,
        kind=kind,
        selection_mask=np.zeros((int(height), int(width)), dtype=np.uint8),
        root=Point(width * 0.5, height * 0.35),
        tip=Point(width * 0.5, height * 0.65),
        root_lock_percent={"hair": 12.0, "cloth": 18.0, "accessory": 5.0, "torso": 20.0}.get(kind, 12.0),
        motion=defaults_for_kind(kind),
    )
