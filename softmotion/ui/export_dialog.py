from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QMessageBox, QSpinBox, QVBoxLayout, QPushButton, QColorDialog,
)

from softmotion.exporting.encoder import ExportCancelled, ExportOptions, export_animation, output_size


class ExportDialog(QDialog):
    def __init__(self, settings, viewport, source_name, parent=None, scene=None):
        super().__init__(parent)
        self.setWindowTitle("导出动态素材")
        self.setMinimumWidth(440)
        self.settings = replace(settings)
        self.scene = scene
        self.mp4_background = "#12151c"
        self.viewport = viewport
        self.source_name = source_name
        self.destination = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        title = QLabel("导出你的动态素材")
        title.setObjectName("title")
        layout.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.format_box = QComboBox()
        for label, key in [("GIF 动图", "gif"), ("MP4 视频", "mp4"), ("PNG 图片序列", "png")]:
            self.format_box.addItem(label, key)
        self.size_box = QComboBox()
        for size in (512, 768, 1024, 1920):
            self.size_box.addItem(f"{size} px", size)
        self.size_box.setCurrentIndex(1)
        self.fps_box = QComboBox()
        for fps in (10, 15, 24, 30, 60):
            self.fps_box.addItem(f"{fps} fps", fps)
        self.fps_box.setCurrentIndex(2)
        self.cycles_box = QSpinBox()
        self.cycles_box.setRange(1, 3)
        form.addRow("导出格式", self.format_box)
        if scene is None:
            form.addRow("画布最长边", self.size_box)
        else:
            form.addRow("输出画布", QLabel(f"{scene.width} × {scene.height} px（在背景与裁剪中修改）"))
        form.addRow("目标帧率", self.fps_box)
        form.addRow("完整循环次数", self.cycles_box)
        layout.addLayout(form)
        self.mp4_color_button = QPushButton("MP4 填充颜色：#12151c")
        self.mp4_color_button.clicked.connect(self.choose_mp4_color)
        layout.addWidget(self.mp4_color_button)
        self.details = QLabel()
        self.details.setObjectName("hint")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("选择位置并导出")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.choose_destination)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for control in (self.format_box, self.size_box, self.fps_box):
            control.currentIndexChanged.connect(self.update_details)
        self.cycles_box.valueChanged.connect(self.update_details)
        self.update_details()

    def options(self):
        return ExportOptions(self.format_box.currentData(), max(self.viewport) if self.scene is not None else self.size_box.currentData(),
                             self.fps_box.currentData(), self.cycles_box.value())

    def update_details(self):
        options = self.options()
        duration, count, fps = options.timing(self.settings)
        width, height = options.size(self.viewport)
        background = "透明背景，附带帧率说明文件。" if options.format == "png" else "使用预览深色背景。"
        if self.scene is not None:
            width, height = output_size(self.scene, options.format)
            background = {"transparent": "透明背景。GIF 使用单级透明，PNG 保留半透明。",
                          "solid": "使用选定的纯色背景。", "image": "使用选定的背景图片。"}[self.scene.background_mode]
            if self.scene.background_mode == "transparent" and options.format == "mp4":
                background = "MP4 不支持透明，将使用所选的填充颜色。"
        self.mp4_color_button.setVisible(self.scene is not None and self.scene.background_mode == "transparent" and options.format == "mp4")
        self.details.setText(
            f"{width} × {height} · {duration:.2f} 秒 · {count} 帧 · {fps:.2f} fps\n\n"
            f"{background}\n保留当前裁剪与构图，从归位姿态开始完整循环。\n"
            "时长由 Speed 和循环次数决定。GIF 帧间隔会按 10 毫秒取整。\n"
            "MP4 奇数宽高会补齐为偶数像素。")

    def choose_mp4_color(self):
        color = QColorDialog.getColor(QColor(self.mp4_background), self, "MP4 填充颜色")
        if color.isValid():
            self.mp4_background = color.name()
            self.mp4_color_button.setText(f"MP4 填充颜色：{color.name()}")

    def choose_destination(self):
        options = self.options()
        if self.scene is not None and self.scene.background_mode == "image" and self.scene.background_image.isNull():
            QMessageBox.warning(self, "尚未选择背景图片", "请返回背景与裁剪，选择背景图片。")
            return
        if options.format == "gif":
            _, count, _ = options.timing(self.settings)
            width, height = options.size(self.viewport)
            if self.scene is not None:
                width, height = output_size(self.scene, options.format)
            if width * height * count > 150_000_000:
                QMessageBox.warning(self, "请降低导出参数", "GIF 帧数据较大，请降低尺寸、帧率或循环次数。")
                return
        name = Path(self.source_name).stem + "_motion"
        if options.format == "png":
            destination, _ = QFileDialog.getSaveFileName(self, "为 PNG 序列指定新文件夹名称", name, "文件夹 (*)")
            if destination and Path(destination).exists():
                QMessageBox.warning(self, "文件夹已存在", "请选择一个尚不存在的文件夹名称。")
                return
        else:
            extension = options.format
            destination, _ = QFileDialog.getSaveFileName(
                self, "保存动画", f"{name}.{extension}", f"{extension.upper()} (*.{extension})")
            if destination and not destination.lower().endswith(f".{extension}"):
                destination += f".{extension}"
                if Path(destination).exists():
                    answer = QMessageBox.question(self, "覆盖文件", f"覆盖 {destination}？")
                    if answer != QMessageBox.StandardButton.Yes:
                        return
        if destination:
            self.destination = Path(destination)
            self.accept()


class ExportWorker(QThread):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, image, viewport, settings, options, destination, parent=None, scene=None, mp4_background=None):
        super().__init__(parent)
        self.image = image.copy()
        self.viewport = viewport
        self.settings = replace(settings)
        self.options = options
        self.destination = destination
        self.scene = scene.snapshot() if scene is not None else None
        self.mp4_background = mp4_background

    def run(self):
        try:
            path = export_animation(self.image, self.viewport, self.settings, self.options,
                                    self.destination, self.progress.emit, self.isInterruptionRequested,
                                    self.scene, self.mp4_background)
        except ExportCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(path))
