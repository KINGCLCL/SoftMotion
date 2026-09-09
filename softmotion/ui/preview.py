from time import perf_counter

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from softmotion.motion.effects import MotionSettings
from softmotion.imaging.render import draw_checkerboard, draw_scene
from softmotion.imaging.scene import SceneSettings
from softmotion.ui.icons import icon


class Preview(QWidget):
    playback_changed = Signal(bool)
    import_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 300)
        self.settings = MotionSettings()
        self.scene = SceneSettings()
        self.pixmap = QPixmap()
        self.image = QImage()
        self.phase = 0.0
        self.playing = False
        self._last_time = perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        empty_layout = QVBoxLayout(self)
        empty_layout.addStretch()
        self.empty_state = QWidget()
        self.empty_state.setObjectName("emptyState")
        content = QVBoxLayout(self.empty_state)
        content.setSpacing(15)
        action = QPushButton("选择一张图片")
        action.setObjectName("primary")
        action.setIcon(icon("image", "#15182b"))
        action.clicked.connect(self.import_requested)
        content.addWidget(action, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.empty_state)
        empty_layout.addStretch()

    def set_image(self, image):
        self.pause()
        self.pixmap = QPixmap.fromImage(image)
        self.image = image.copy()
        self.empty_state.hide()
        self.scene.crop = (0, 0, image.width(), image.height())
        self.phase = 0.0
        self.update()
        self.play()

    def play(self):
        if self.pixmap.isNull() or self.playing:
            return
        self.playing = True
        self._last_time = perf_counter()
        self.timer.start()
        self.playback_changed.emit(True)

    def pause(self):
        if self.playing:
            self._advance()
        self.playing = False
        self.timer.stop()
        self.update()
        self.playback_changed.emit(False)

    def reset(self):
        """Pause and restore both the neutral pose and restrained defaults."""
        self.pause()
        self.phase = 0.0
        self.settings = MotionSettings()
        self.update()

    def set_parameter(self, name, value):
        if self.playing:
            self._advance()
        setattr(self.settings, name, value)
        self.update()

    def _advance(self):
        now = perf_counter()
        # Speed changes affect future phase only. Pause time is never included.
        self.phase = (self.phase + (now - self._last_time) * self.settings.speed / 5.0) % 1.0
        self._last_time = now

    def _tick(self):
        self._advance()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#131720"))
        painter.setPen(QColor("#272e3d"))
        for x in range(16, self.width(), 24):
            for y in range(16, self.height(), 24):
                painter.drawPoint(x, y)
        if self.pixmap.isNull():
            return
        scale = min((self.width() - 24) / self.scene.width,
                    (self.height() - 24) / self.scene.height)
        left = (self.width() - self.scene.width * scale) / 2
        top = (self.height() - self.scene.height * scale) / 2
        rect = QRectF(left, top, self.scene.width * scale, self.scene.height * scale)
        if self.scene.background_mode == "transparent":
            draw_checkerboard(painter, rect)
        painter.save()
        painter.translate(left, top)
        painter.scale(scale, scale)
        draw_scene(painter, self.image, self.scene, self.phase, self.settings)
        painter.restore()
        painter.setPen(QColor("#58647a"))
        painter.drawRect(rect)
