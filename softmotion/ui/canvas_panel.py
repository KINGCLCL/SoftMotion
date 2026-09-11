from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QFormLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from softmotion.imaging.loader import load_image
from softmotion.imaging.render import draw_checkerboard


class CropView(QWidget):
    crop_changed = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.image = QImage()
        self.crop = (0, 0, 1, 1)
        self.start = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self):
        if self.image.isNull():
            return QRectF()
        fit = min((self.width() - 8) / self.image.width(), (self.height() - 8) / self.image.height())
        w, h = self.image.width() * fit, self.image.height() * fit
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.image.isNull():
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "导入图片后可拖动框选 Import an image, then drag to crop")
            return
        rect = self.image_rect()
        draw_checkerboard(painter, rect)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.35)
        painter.drawImage(rect, self.image)
        painter.setOpacity(1)
        x, y, w, h = self.crop
        factor = rect.width() / self.image.width()
        selected = QRectF(rect.x() + x * factor, rect.y() + y * factor, w * factor, h * factor)
        painter.save()
        painter.setClipRect(selected)
        painter.drawImage(rect, self.image)
        painter.restore()
        painter.setPen(QColor("#a5b4ff"))
        painter.drawRect(selected)

    def source_point(self, position):
        rect = self.image_rect()
        factor = self.image.width() / rect.width()
        return QPointF(max(0, min(self.image.width(), (position.x() - rect.x()) * factor)),
                       max(0, min(self.image.height(), (position.y() - rect.y()) * factor)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.image.isNull():
            self.start = self.source_point(event.position())

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.select_to(event.position())

    def mouseReleaseEvent(self, event):
        if self.start is not None and event.button() == Qt.MouseButton.LeftButton:
            self.select_to(event.position())
            self.start = None

    def select_to(self, position):
        end = self.source_point(position)
        x = min(self.image.width() - 1, int(min(self.start.x(), end.x())))
        y = min(self.image.height() - 1, int(min(self.start.y(), end.y())))
        w = max(1, min(self.image.width() - x, round(max(self.start.x(), end.x())) - x))
        h = max(1, min(self.image.height() - y, round(max(self.start.y(), end.y())) - y))
        self.crop_changed.emit((x, y, w, h))


class CanvasPanel(QWidget):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.preview = preview
        self.setObjectName("inspector")
        self._syncing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel("输出画布 Output Canvas")
        title.setObjectName("section")
        layout.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.width_box = QSpinBox()
        self.height_box = QSpinBox()
        for box, value in [(self.width_box, preview.scene.width), (self.height_box, preview.scene.height)]:
            box.setRange(64, 1920)
            box.setValue(value)
            box.setSuffix(" px")
            box.valueChanged.connect(self.update_scene)
        form.addRow("输出宽度 Width", self.width_box)
        form.addRow("输出高度 Height", self.height_box)
        self.background_box = QComboBox()
        for name, value in [("透明 Transparent", "transparent"), ("纯色 Solid Color", "solid"), ("自选图片 Custom Image", "image")]:
            self.background_box.addItem(name, value)
        self.background_box.currentIndexChanged.connect(self.update_scene)
        form.addRow("背景 Background", self.background_box)
        layout.addLayout(form)
        self.color_button = QPushButton("背景颜色 Background Color：#12151c")
        self.color_button.clicked.connect(self.choose_color)
        layout.addWidget(self.color_button)
        self.background_button = QPushButton("选择背景图片… Choose Background Image…")
        self.background_button.clicked.connect(self.choose_background)
        layout.addWidget(self.background_button)
        label = QLabel("素材裁剪 Crop")
        label.setObjectName("section")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.crop_view = CropView()
        self.crop_view.setToolTip("在缩略图上拖动框选，或在下方输入精确坐标 Drag on the thumbnail to crop, or enter exact coordinates below")
        self.crop_view.crop_changed.connect(self.set_crop)
        layout.addWidget(self.crop_view)
        crop_form = QFormLayout()
        crop_form.setVerticalSpacing(8)
        self.crop_boxes = []
        for label in ("左侧 X Left X", "顶部 Y Top Y", "裁剪宽度 Crop Width", "裁剪高度 Crop Height"):
            box = QSpinBox()
            box.setRange(0, 2048)
            box.valueChanged.connect(self.crop_edited)
            crop_form.addRow(label, box)
            self.crop_boxes.append(box)
        layout.addLayout(crop_form)
        reset = QPushButton("恢复完整素材 Restore Full Image")
        reset.clicked.connect(self.reset_crop)
        layout.addWidget(reset)
        self.info = QLabel("裁剪不修改原文件。棋盘格仅用于预览透明度。 Cropping keeps the original file intact. The checkerboard previews transparency.\n背景图居中铺满画布；素材原有背景不会被自动移除。 The background image fills the canvas from the center. Existing asset backgrounds are not removed automatically.")
        self.info.setWordWrap(True)
        self.info.setObjectName("hint")
        layout.addWidget(self.info)
        layout.addStretch()
        self.update_scene()

    def update_scene(self):
        scene = self.preview.scene
        scene.width, scene.height = self.width_box.value(), self.height_box.value()
        scene.background_mode = self.background_box.currentData()
        self.color_button.setVisible(scene.background_mode != "transparent")
        self.background_button.setVisible(scene.background_mode == "image")
        self.preview.update()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.preview.scene.background_color), self, "选择背景颜色 Choose Background Color")
        if color.isValid():
            self.preview.scene.background_color = color.name()
            self.color_button.setText(f"背景颜色 Background Color：{color.name()}")
            self.preview.update()

    def choose_background(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图片 Choose Background Image", "", "图片 Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            try:
                asset = load_image(path)
            except ValueError as exc:
                QMessageBox.warning(self, "背景导入失败 Background Import Failed", str(exc))
                return
            self.preview.scene.background_image = asset.preview
            self.background_button.setText("已选背景 · 点击更换 Background Selected · Click to Change")
            self.background_button.setToolTip(str(asset.path))
            self.preview.update()

    def set_source(self, image):
        self.crop_view.image = image.copy()
        self.info.setText(f"裁剪坐标基于载入图： Crop coordinates use the loaded image:{image.width()} × {image.height()} px（最长边 2048）。  (Longest edge: 2048).\n"
                          "裁剪不修改原文件。棋盘格不会导出。 Cropping keeps the original file intact. The checkerboard is not exported.\n背景图居中铺满画布；素材原有背景不会被自动移除。 The background image fills the canvas from the center. Existing asset backgrounds are not removed automatically.")
        self.reset_crop()

    def set_scene(self, scene):
        """Synchronize controls from a loaded project scene."""
        self._syncing = True
        self.width_box.setValue(scene.width)
        self.height_box.setValue(scene.height)
        self.background_box.setCurrentIndex(self.background_box.findData(scene.background_mode))
        self.preview.scene.background_color = scene.background_color
        self.color_button.setText(f"背景颜色 Background Color：{scene.background_color}")
        self.background_button.setText("已选背景 · 点击更换 Background Selected · Click to Change"
                                      if scene.background_mode == "image" and not scene.background_image.isNull()
                                      else "选择背景图片… Choose Background Image…")
        self._syncing = False
        self.update_scene()
        self.set_crop(scene.crop or (0, 0, self.preview.image.width(), self.preview.image.height()))

    def reset_crop(self):
        image = self.preview.image
        if not image.isNull():
            self.set_crop((0, 0, image.width(), image.height()))

    def set_crop(self, crop):
        image = self.preview.image
        if image.isNull():
            return
        x, y, w, h = crop
        x, y = min(max(0, x), image.width() - 1), min(max(0, y), image.height() - 1)
        w, h = max(1, min(w, image.width() - x)), max(1, min(h, image.height() - y))
        crop = (x, y, w, h)
        self._syncing = True
        for box, minimum, maximum, value in zip(self.crop_boxes, (0, 0, 1, 1),
                                                (image.width() - 1, image.height() - 1,
                                                 image.width() - x, image.height() - y), crop):
            box.setRange(minimum, maximum)
            box.setValue(value)
        self._syncing = False
        self.preview.scene.crop = crop
        self.crop_view.crop = crop
        self.crop_view.update()
        self.preview.update()

    def crop_edited(self):
        if not self._syncing:
            self.set_crop(tuple(box.value() for box in self.crop_boxes))
