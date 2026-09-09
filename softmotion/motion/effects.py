from dataclasses import dataclass
from math import sin, tau


@dataclass
class MotionSettings:
    float_px: float = 3.0
    breath_percent: float = 0.6
    sway_degrees: float = 0.4
    speed: float = 1.0
    idle_breath_percent: float = 0.0
    weight_shift_px: float = 0.0
    lean_degrees: float = 0.0
    anchor_feet: bool = False


@dataclass(frozen=True)
class Pose:
    y: float
    scale: float
    rotation: float
    stretch_x: float = 1.0
    stretch_y: float = 1.0
    weight_shift: float = 0.0
    lean: float = 0.0


def sample_pose(phase: float, settings: MotionSettings) -> Pose:
    """Always sample from the original pose; never transform the previous frame.

    Phase is measured in cycles. A single shared period keeps looping seamless.
    """
    wave = sin(tau * (phase % 1.0))
    return Pose(-settings.float_px * wave,
                1.0 + settings.breath_percent / 100.0 * wave,
                settings.sway_degrees * wave,
                1.0 - settings.idle_breath_percent / 100.0 * wave * 0.3,
                1.0 + settings.idle_breath_percent / 100.0 * wave,
                settings.weight_shift_px * (wave + 0.2 * sin(2 * tau * (phase % 1.0))),
                settings.lean_degrees * wave)


PRESETS = {
    "轻柔漂浮": MotionSettings(),
    "人物 · 自然待机": MotionSettings(0, 0, 0, 0.8, 0.8, 2.0, 0.25, True),
    "人物 · 警戒待机": MotionSettings(0, 0, 0, 1.1, 0.5, 1.0, 0.2, True),
    "人物 · 疲惫待机": MotionSettings(0, 0, 0, 0.6, 1.5, 4.0, 0.6, True),
}
