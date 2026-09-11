from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from pathlib import Path
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QVBoxLayout, QWidget, QDialog, QProgressDialog, QTabWidget, QScrollArea,
)

from softmotion.imaging.loader import load_image
from softmotion.ui.preview import Preview
from softmotion.ui.export_dialog import ExportDialog, ExportWorker
from softmotion.ui.motion_panel import MotionPanel
from softmotion.ui.canvas_panel import CanvasPanel
from softmotion.ui.character_panel import CharacterPanel
from softmotion.character.project import load_project, save_project
from softmotion.ui.icons import icon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.export_worker = None
        self.source_name = "image"
        self.project_path = None
        self.setWindowTitle("SoftMotion — V0.1")
        self.resize(1240, 900)
        self.setMinimumSize(920, 650)
        self.setWindowIcon(icon("wave", "#a4adff", 32))
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_frame = QFrame()
        header_frame.setObjectName("header")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(24, 18, 24, 18)
        header.setSpacing(16)
        mark = QLabel()
        mark.setPixmap(icon("wave", "#a4adff", 40).pixmap(40, 40))
        header.addWidget(mark)
        branding = QVBoxLayout()
        branding.setSpacing(2)
        title = QLabel("SoftMotion")
        title.setObjectName("title")
        branding.addWidget(title)
        header.addLayout(branding)
        badge = QLabel("V0.1")
        badge.setObjectName("badge")
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch()
        self.import_button = QPushButton("导入图片 Import Image")
        self.import_button.setIcon(icon("image"))
        self.import_button.setToolTip("导入 PNG / JPG / WebP Import PNG / JPG / WebP · Ctrl+O")
        self.import_button.clicked.connect(self.choose_image)
        header.addWidget(self.import_button)
        self.export_button = QPushButton("导出素材 Export Asset")
        self.export_button.setObjectName("primary")
        self.export_button.setIcon(icon("export", "#15182b"))
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.choose_export)
        header.addWidget(self.export_button)
        layout.addWidget(header_frame)
        project_menu = self.menuBar().addMenu("工程 Project")
        open_action = QAction("打开工程 Open Project", self)
        open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_action.triggered.connect(self.choose_open_project)
        project_menu.addAction(open_action)
        self.save_project_action = QAction("保存工程 Save Project", self)
        self.save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_project_action.setEnabled(False)
        self.save_project_action.triggered.connect(self.choose_save_project)
        project_menu.addAction(self.save_project_action)

        body = QHBoxLayout()
        body.setContentsMargins(22, 22, 22, 22)
        body.setSpacing(20)
        stage = QFrame()
        stage.setObjectName("stage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(1, 1, 1, 1)
        stage_layout.setSpacing(0)
        stage_bar = QWidget()
        stage_bar.setObjectName("stageBar")
        stage_header = QHBoxLayout(stage_bar)
        stage_header.setContentsMargins(18, 14, 18, 14)
        stage_title = QLabel("画布预览 Preview")
        stage_title.setObjectName("section")
        stage_header.addWidget(stage_title)
        stage_header.addStretch()
        self.canvas_label = QLabel("768 × 768  ·  透明 Transparent")
        self.canvas_label.setObjectName("muted")
        stage_header.addWidget(self.canvas_label)
        stage_layout.addWidget(stage_bar)
        self.preview = Preview()
        self.preview.import_requested.connect(self.choose_image)
        stage_layout.addWidget(self.preview, 1)
        body.addWidget(stage, 1)
        tabs = QTabWidget()
        tabs.setFixedWidth(430)
        self.motion_panel = MotionPanel(self.preview)
        self.canvas_panel = CanvasPanel(self.preview)
        self.character_panel = CharacterPanel(self.preview)
        self.sliders = self.motion_panel.sliders
        self.defaults = self.motion_panel.defaults
        self.canvas_panel.width_box.valueChanged.connect(self.refresh_canvas_label)
        self.canvas_panel.height_box.valueChanged.connect(self.refresh_canvas_label)
        self.canvas_panel.background_box.currentIndexChanged.connect(self.refresh_canvas_label)
        for label, panel in [("动态效果 Motion", self.motion_panel), ("人物部位 Character Parts", self.character_panel),
                             ("背景与裁剪 Background && Crop", self.canvas_panel)]:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(panel)
            tabs.addTab(scroll, label)
        body.addWidget(tabs)
        layout.addLayout(body, 1)

        transport = QFrame()
        transport.setObjectName("transport")
        footer = QHBoxLayout(transport)
        footer.setContentsMargins(16, 14, 16, 14)
        footer.setSpacing(8)
        self.file_label = QLabel("未选择素材 No asset selected\n导入图片以开始预览 Import an image to preview")
        self.file_label.setObjectName("muted")
        self.file_label.setMinimumWidth(0)
        footer.addWidget(self.file_label, 1)
        self.play_button = QPushButton("播放 Play")
        self.play_button.setObjectName("primary")
        self.play_button.setIcon(icon("play", "#15182b"))
        self.pause_button = QPushButton("暂停 Pause")
        self.pause_button.setIcon(icon("pause"))
        self.reset_button = QPushButton()
        self.reset_button.setObjectName("quiet")
        self.reset_button.setIcon(icon("reset"))
        self.reset_button.setAccessibleName("Reset · 重置动态")
        self.reset_button.setToolTip("重置动态参数并暂停归位，保留背景与裁剪 Reset motion and pause at the starting pose; keep background and crop")
        for button, callback in [(self.play_button, self.preview.play),
                                 (self.pause_button, self.preview.pause),
                                 (self.reset_button, self.reset)]:
            button.clicked.connect(callback)
            button.setEnabled(False)
            footer.addWidget(button)
        stage_layout.addWidget(transport)
        self.preview.playback_changed.connect(self.update_playback)
        self.statusBar().showMessage("就绪 · 支持透明图片 Ready · Transparent images supported")
        status_note = QLabel("本地处理 Local processing  ·  PNG / JPG / WebP")
        status_note.setObjectName("subtitle")
        self.statusBar().addPermanentWidget(status_note)
        shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut.activated.connect(self.choose_image)

    def refresh_canvas_label(self):
        scene = self.preview.scene
        background = {"transparent": "透明 Transparent", "solid": "纯色 Solid Color", "image": "图片背景 Image Background"}[scene.background_mode]
        self.canvas_label.setText(f"{scene.width} × {scene.height}  ·  {background}")

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入静态图片 Import Still Image", "", "图片 Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.open_image(path)

    def open_image(self, path):
        try:
            asset = load_image(path)
        except ValueError as exc:
            QMessageBox.warning(self, "导入失败 Import Failed", str(exc))
            return False
        name = asset.path.name if len(asset.path.name) <= 24 else asset.path.stem[:20] + "…" + asset.path.suffix
        self.file_label.setText(f"{name}\n{asset.width} × {asset.height} px")
        self.file_label.setToolTip(str(asset.path))
        self.preview.set_image(asset.preview)
        self.motion_panel.reset()
        self.canvas_panel.set_source(asset.preview)
        self.character_panel.set_image(asset.preview)
        self.source_name = asset.path.name
        self.project_path = None
        self.export_button.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.reset_button.setEnabled(True)
        return True

    def choose_open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 SoftMotion 工程 Open SoftMotion Project", "", "SoftMotion 工程 (*.softmotion)")
        if path:
            self.open_project(path)

    def open_project(self, path):
        try:
            project = load_project(path)
        except ValueError as exc:
            QMessageBox.warning(self, "打开工程失败 Open Project Failed", str(exc))
            return False
        self.preview.pause()
        self.preview.set_image(project.source)
        self.preview.settings = project.motion
        self.motion_panel.sync(project.motion)
        self.canvas_panel.set_source(project.source)
        self.preview.scene = project.scene
        self.canvas_panel.set_scene(project.scene)
        self.character_panel.set_image(project.source)
        self.character_panel.set_settings(project.character)
        self.source_name = project.source_name
        self.project_path = Path(path)
        self.export_button.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.reset_button.setEnabled(True)
        self.refresh_canvas_label()
        return True

    def choose_save_project(self):
        if self.preview.image.isNull():
            return
        default = str(self.project_path or (Path(self.source_name).with_suffix(".softmotion")))
        path, _ = QFileDialog.getSaveFileName(self, "保存 SoftMotion 工程 Save SoftMotion Project", default, "SoftMotion 工程 (*.softmotion)")
        if path:
            if Path(path).suffix.lower() != ".softmotion":
                path += ".softmotion"
            self.save_project(path)

    def save_project(self, path):
        try:
            save_project(path, self.preview.image, self.source_name, self.preview.settings,
                         self.preview.scene, self.preview.character)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存工程失败 Save Project Failed", str(exc))
            return False
        self.project_path = Path(path)
        self.statusBar().showMessage(f"工程已保存 Project saved: {path}")
        return True

    def update_playback(self, playing):
        loaded = not self.preview.pixmap.isNull()
        self.play_button.setEnabled(loaded and not playing)
        self.pause_button.setEnabled(loaded and playing)
        self.statusBar().showMessage("播放中 · 实时预览 Playing · Live preview" if playing else "已暂停 Paused" if loaded else "就绪 Ready")

    def reset(self):
        self.preview.reset()
        self.motion_panel.reset()

    def closeEvent(self, event):
        if self.export_worker is not None and self.export_worker.isRunning():
            self.statusBar().showMessage("请等待导出完成，或先取消导出再关闭窗口。 Wait for export to finish, or cancel it before closing.")
            event.ignore()
            return
        self.preview.pause()
        super().closeEvent(event)

    def choose_export(self):
        if self.export_worker is not None:
            return
        scene = self.preview.scene.snapshot()
        viewport = (scene.width, scene.height)
        dialog = ExportDialog(self.preview.settings, viewport, self.source_name, self, scene=scene)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.export_button.setEnabled(False)
        self.export_progress = QProgressDialog("正在生成动画帧… Generating animation frames…", "取消 Cancel", 0, 100, self)
        self.export_progress.setWindowTitle("导出 Export")
        self.export_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.export_progress.setAutoClose(False)
        self.export_progress.setAutoReset(False)
        self.export_progress.setMinimumDuration(0)
        self.export_worker = ExportWorker(self.preview.image, viewport, dialog.settings,
                                          dialog.options(), dialog.destination, self, scene=scene,
                                          mp4_background=dialog.mp4_background,
                                          character=self.preview.character)
        self.export_worker.progress.connect(self.export_progress.setValue)
        self.export_progress.canceled.connect(self.cancel_export)
        self.export_worker.succeeded.connect(self.export_succeeded)
        self.export_worker.failed.connect(self.export_failed)
        self.export_worker.cancelled.connect(self.export_cancelled)
        self.export_worker.finished.connect(self.export_finished)
        self.export_worker.start()
        self.export_progress.show()

    def cancel_export(self):
        if self.export_worker is not None:
            self.export_worker.requestInterruption()
            self.statusBar().showMessage("正在取消导出… Cancelling export…")

    def export_succeeded(self, path):
        self.export_progress.close()
        QMessageBox.information(self, "导出完成 Export Complete", f"已保存至： Saved to:\n{path}")

    def export_failed(self, message):
        self.export_progress.close()
        QMessageBox.warning(self, "导出失败 Export Failed", message)

    def export_cancelled(self):
        self.export_progress.close()
        self.statusBar().showMessage("已取消导出，临时文件已清理。 Export cancelled; temporary files removed.")

    def export_finished(self):
        self.export_worker.deleteLater()
        self.export_worker = None
        self.export_progress.deleteLater()
        self.export_button.setEnabled(True)
