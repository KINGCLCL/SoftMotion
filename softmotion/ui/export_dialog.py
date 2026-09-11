from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QMessageBox, QSpinBox, QVBoxLayout, QPushButton, QColorDialog,
)

from softmotion.exporting.encoder import ExportCancelled, ExportOptions, export_animation, output_size
from softmotion.character.model import CharacterSettings


class ExportDialog(QDialog):
    def __init__(self, settings, viewport, source_name, parent=None, scene=None):
        super().__init__(parent)
        self.setWindowTitle("导出动态素材 Export Animation")
        self.setMinimumWidth(640)
        self.settings = replace(settings)
        self.scene = scene
        self.mp4_background = "#12151c"
        self.viewport = viewport
        self.source_name = source_name
        self.destination = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        title = QLabel("导出你的动态素材 Export Your Animation")
        title.setObjectName("title")
        layout.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.format_box = QComboBox()
        for label, key in [("GIF 动图 GIF Animation", "gif"), ("MP4 视频 MP4 Video", "mp4"), ("PNG 图片序列 PNG Sequence", "png")]:
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
        form.addRow("导出格式 Format", self.format_box)
        if scene is None:
            form.addRow("画布最长边 Longest Edge", self.size_box)
        else:
            canvas_info = QLabel(f"{scene.width} × {scene.height} px（在背景与裁剪中修改） (Edit in Background & Crop)")
            canvas_info.setWordWrap(True)
            form.addRow("输出画布 Output Canvas", canvas_info)
        form.addRow("目标帧率 Frame Rate", self.fps_box)
        form.addRow("完整循环次数 Loops", self.cycles_box)
        layout.addLayout(form)
        self.mp4_color_button = QPushButton("MP4 填充颜色 MP4 Fill Color：#12151c")
        self.mp4_color_button.clicked.connect(self.choose_mp4_color)
        layout.addWidget(self.mp4_color_button)
        self.details = QLabel()
        self.details.setObjectName("hint")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("选择位置并导出 Choose Location && Export")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消 Cancel")
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
        background = "透明背景，附带帧率说明文件。 Transparent background with frame-rate metadata." if options.format == "png" else "使用预览深色背景。 Use the dark preview background."
        if self.scene is not None:
            width, height = output_size(self.scene, options.format)
            background = {"transparent": "透明背景。GIF 使用单级透明，PNG 保留半透明。 Transparent background. GIF uses binary transparency; PNG preserves partial transparency.",
                          "solid": "使用选定的纯色背景。 Use the selected solid background.", "image": "使用选定的背景图片。 Use the selected background image."}[self.scene.background_mode]
            if self.scene.background_mode == "transparent" and options.format == "mp4":
                background = "MP4 不支持透明，将使用所选的填充颜色。 MP4 does not support transparency; the selected fill color will be used."
        self.mp4_color_button.setVisible(self.scene is not None and self.scene.background_mode == "transparent" and options.format == "mp4")
        self.details.setText(
            f"{width} × {height} · {duration:.2f} 秒 s · {count} 帧 frames · {fps:.2f} fps\n\n"
            f"{background}\n保留当前裁剪与构图，从归位姿态开始完整循环。 Keep the current crop and composition; export full loops from the starting pose.\n"
            "时长由 Speed 和循环次数决定。GIF 帧间隔会按 10 毫秒取整。 Duration depends on Speed and loop count. GIF frame intervals are rounded to 10 ms.\n"
            "MP4 奇数宽高会补齐为偶数像素。 Odd MP4 dimensions are padded to even pixels.")

    def choose_mp4_color(self):
        color = QColorDialog.getColor(QColor(self.mp4_background), self, "MP4 填充颜色 MP4 Fill Color")
        if color.isValid():
            self.mp4_background = color.name()
            self.mp4_color_button.setText(f"MP4 填充颜色 MP4 Fill Color：{color.name()}")

    def choose_destination(self):
        options = self.options()
        if self.scene is not None and self.scene.background_mode == "image" and self.scene.background_image.isNull():
            QMessageBox.warning(self, "尚未选择背景图片 No Background Image", "请返回背景与裁剪，选择背景图片。 Select a background image in Background & Crop.")
            return
        if options.format == "gif":
            _, count, _ = options.timing(self.settings)
            width, height = options.size(self.viewport)
            if self.scene is not None:
                width, height = output_size(self.scene, options.format)
            if width * height * count > 150_000_000:
                QMessageBox.warning(self, "请降低导出参数 Reduce Export Settings", "GIF 帧数据较大，请降低尺寸、帧率或循环次数。 GIF frame data is too large. Reduce dimensions, frame rate, or loop count.")
                return
        name = Path(self.source_name).stem + "_motion"
        if options.format == "png":
            destination, _ = QFileDialog.getSaveFileName(self, "为 PNG 序列指定新文件夹名称 Choose a New Folder Name for the PNG Sequence", name, "文件夹 Folders (*)")
            if destination and Path(destination).exists():
                QMessageBox.warning(self, "文件夹已存在 Folder Exists", "请选择一个尚不存在的文件夹名称。 Choose a folder name that does not already exist.")
                return
        else:
            extension = options.format
            destination, _ = QFileDialog.getSaveFileName(
                self, "保存动画 Save Animation", f"{name}.{extension}", f"{extension.upper()} (*.{extension})")
            if destination and not destination.lower().endswith(f".{extension}"):
                destination += f".{extension}"
                if Path(destination).exists():
                    answer = QMessageBox.question(self, "覆盖文件 Overwrite File", f"覆盖 {destination}？ Overwrite {destination}?")
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

    def __init__(self, image, viewport, settings, options, destination, parent=None, scene=None, mp4_background=None, character=None):
        super().__init__(parent)
        self.image = image.copy()
        self.viewport = viewport
        self.settings = replace(settings)
        self.options = options
        self.destination = destination
        self.scene = scene.snapshot() if scene is not None else None
        self.mp4_background = mp4_background
        self.character = character.snapshot() if character is not None else CharacterSettings()

    def run(self):
        try:
            path = export_animation(self.image, self.viewport, self.settings, self.options,
                                    self.destination, self.progress.emit, self.isInterruptionRequested,
                                    self.scene, self.mp4_background, self.character)
        except ExportCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(path))
