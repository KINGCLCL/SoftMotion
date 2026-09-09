"""Canvas settings in output pixels, independent of the desktop window size."""
from dataclasses import dataclass, field, replace

from PySide6.QtGui import QImage


@dataclass
class SceneSettings:
    width: int = 768
    height: int = 768
    background_mode: str = "transparent"
    background_color: str = "#12151c"
    background_image: QImage = field(default_factory=QImage)
    # Coordinates refer to the decoded source preview (at most 2048 px per side).
    crop: tuple[int, int, int, int] | None = None

    def snapshot(self):
        return replace(self, background_image=self.background_image.copy())

    def metadata(self):
        return {"width": self.width, "height": self.height,
                "background": self.background_mode, "color": self.background_color,
                "crop": self.crop}
