from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from softmotion.character.model import CharacterSettings, PartMotion, Point, defaults_for_kind, new_region
from softmotion.ui.region_editor import RegionEditor


class CharacterPanel(QWidget):
    """Edit masks and motion controls for hand-selected character parts."""

    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.preview = preview
        self.settings = CharacterSettings()
        self._syncing = False
        self.setObjectName("inspector")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("人物部位 Character Parts")
        title.setObjectName("section")
        layout.addWidget(title)
        self.enabled_box = QCheckBox("启用人物部位动画\nEnable character part animation")
        self.enabled_box.setChecked(True)
        self.enabled_box.toggled.connect(self._toggle_enabled)
        layout.addWidget(self.enabled_box)
        self.editor = RegionEditor()
        self.editor.editing_changed.connect(self.preview.set_character_editing)
        self.editor.changed.connect(self._editor_changed)
        self.editor.point_changed.connect(self._refresh_controls)
        layout.addWidget(self.editor)

        self.tools_widget = QWidget()
        tools = QHBoxLayout(self.tools_widget)
        tools.setContentsMargins(0, 0, 0, 0)
        self.tool_box = QComboBox()
        for label, value in [("画笔 Brush", "brush"), ("橡皮 Eraser", "erase"),
                             ("套索 Lasso", "lasso"), ("椭圆 Ellipse", "ellipse"),
                             ("保护区 Protect", "protect"), ("擦除保护区", "protect_erase")]:
            self.tool_box.addItem(label, value)
        self.tool_box.currentIndexChanged.connect(lambda index: self._set_tool(self.tool_box.itemData(index)))
        tools.addWidget(self.tool_box, 1)
        self.brush_size = QSpinBox()
        self.brush_size.setRange(1, 256)
        self.brush_size.setValue(18)
        self.brush_size.setSuffix(" px")
        self.brush_size.valueChanged.connect(lambda value: setattr(self.editor, "brush_radius", float(value)))
        tools.addWidget(self.brush_size)
        undo = QPushButton("撤销 Undo")
        undo.clicked.connect(self.editor.undo_stack.undo)
        tools.addWidget(undo)
        layout.addWidget(self.tools_widget)
        enlarge = QPushButton("放大编辑区域")
        enlarge.clicked.connect(self.enlarge_editor)
        layout.addWidget(enlarge)

        list_title = QLabel("已选部位 Selected Parts")
        list_title.setObjectName("eyebrow")
        layout.addWidget(list_title)
        self.region_list = QListWidget()
        self.region_list.setMaximumHeight(125)
        self.region_list.currentRowChanged.connect(self._select_row)
        self.region_list.itemChanged.connect(self._item_enabled_changed)
        layout.addWidget(self.region_list)
        buttons = QHBoxLayout()
        for label, callback in [("新增 Add", self.add_region), ("复制 Copy", self.copy_region), ("删除 Delete", self.delete_region)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.preview_only_box = QCheckBox("仅预览当前部位\nPreview selected part only")
        self.preview_only_box.toggled.connect(self._editor_changed)
        layout.addWidget(self.preview_only_box)

        self.form = QFormLayout()
        self.form.setVerticalSpacing(7)
        self.name_box = QComboBox()
        self.name_box.setEditable(True)
        self.name_box.lineEdit().editingFinished.connect(self._name_changed)
        self.kind_box = QComboBox()
        for label, value in [("头发 Hair", "hair"), ("衣摆／袖口 Cloth", "cloth"),
                             ("饰品 Accessory", "accessory"), ("身体／胸肩 Torso", "torso")]:
            self.kind_box.addItem(label, value)
        self.kind_box.currentIndexChanged.connect(self._kind_changed)
        self.form.addRow("名称 Name", self.name_box)
        self.form.addRow("部位类型 Type", self.kind_box)
        self.amplitude_box = self._double(0, 30, 3, 0.1, "%")
        self.angle_box = self._double(0, 20, 3, 0.1, "°")
        self.cycles_box = QSpinBox(); self.cycles_box.setRange(1, 4)
        self.phase_box = self._double(0, 1, 0, 0.01, "")
        self.lag_box = self._double(0, 0.35, 0.12, 0.01, "")
        self.bend_box = self._double(0.1, 4, 1.8, 0.1, "")
        self.width_ratio_box = self._double(0, 1, 0.15, 0.01, "")
        self.lock_box = self._double(0, 95, 12, 1, "%")
        self.feather_box = self._double(0, 30, 8, 1, "%")
        for label, control in [("摆动幅度 Amplitude", self.amplitude_box), ("旋转幅度 Angle", self.angle_box),
                               ("每轮次数 Cycles", self.cycles_box), ("相位偏移 Phase", self.phase_box),
                               ("末端延迟 Tip Lag", self.lag_box), ("弯曲指数 Bend", self.bend_box),
                               ("身体宽度 Width", self.width_ratio_box), ("根部固定 Root Lock", self.lock_box),
                               ("边缘过渡 Feather", self.feather_box)]:
            self.form.addRow(label, control)
        for control in (self.amplitude_box, self.angle_box, self.cycles_box, self.phase_box,
                        self.lag_box, self.bend_box, self.width_ratio_box, self.lock_box, self.feather_box):
            control.valueChanged.connect(self._motion_changed)
        layout.addLayout(self.form)
        point_buttons = QHBoxLayout()
        self.root_button = QPushButton("设置固定端 Root")
        self.tip_button = QPushButton("设置活动端 Tip")
        self.root_button.clicked.connect(lambda: self._set_anchor("root"))
        self.tip_button.clicked.connect(lambda: self._set_anchor("tip"))
        point_buttons.addWidget(self.root_button); point_buttons.addWidget(self.tip_button)
        layout.addLayout(point_buttons)
        reset = QPushButton("恢复该部位默认值 Reset Part Defaults")
        reset.clicked.connect(self.reset_region)
        layout.addWidget(reset)
        hint = QLabel("先新增部位，再用画笔、套索或椭圆选择区域；绿色点是固定端，黄色点是活动端。\nAdd a part, select it with a brush/lasso/ellipse, then place the green root and yellow tip.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        layout.addStretch()
        self._set_controls_enabled(False)

    @staticmethod
    def _double(minimum, maximum, value, step, suffix):
        box = QDoubleSpinBox()
        box.setKeyboardTracking(False)
        box.setRange(minimum, maximum); box.setSingleStep(step); box.setValue(value); box.setSuffix(suffix)
        return box

    def set_image(self, image):
        self.settings = CharacterSettings()
        self.preview_only_box.blockSignals(True)
        self.preview_only_box.setChecked(False)
        self.preview_only_box.blockSignals(False)
        self.editor.set_image(image)
        self.editor.set_settings(self.settings)
        self._refresh_list()
        self._changed()

    def set_settings(self, settings):
        self.settings = settings.snapshot()
        self.editor.set_settings(self.settings)
        self.preview_only_box.blockSignals(True)
        self.preview_only_box.setChecked(False)
        self.preview_only_box.blockSignals(False)
        self.enabled_box.blockSignals(True)
        self.enabled_box.setChecked(self.settings.enabled)
        self.enabled_box.blockSignals(False)
        self._refresh_list()
        self._refresh_controls()
        self.preview.set_character_settings(self.settings)

    def _effective_settings(self):
        from dataclasses import replace
        result = replace(self.settings, regions=[replace(r) for r in self.settings.regions])
        if self.preview_only_box.isChecked() and self.editor.current_id:
            for region in result.regions:
                region.enabled = region.id == self.editor.current_id
        return result

    def _changed(self):
        self.preview.set_character_settings(self._effective_settings())
        self.editor.update()
        self._refresh_controls()

    def _editor_changed(self):
        self.settings.bump()
        self._changed()

    def _toggle_enabled(self, enabled):
        self.settings.enabled = enabled
        self._editor_changed()

    def add_region(self):
        if self.editor.image.isNull():
            return
        index = len(self.settings.regions) + 1
        self.settings.regions.append(new_region(self.editor.image.width(), self.editor.image.height(), f"部位 {index}"))
        self.editor.current_id = self.settings.regions[-1].id
        self.tool_box.setCurrentIndex(0)
        self._set_tool("brush")
        self._refresh_list()
        self._changed()

    def copy_region(self):
        region = self.editor.region()
        if region is None:
            return
        clone = region.snapshot()
        from uuid import uuid4
        clone.id = uuid4().hex
        clone.name = f"{region.name} 副本"
        self.settings.regions.append(clone)
        self.editor.current_id = clone.id
        self._refresh_list(); self._changed()

    def delete_region(self):
        if self.editor.current_id is None:
            return
        self.settings.regions = [region for region in self.settings.regions if region.id != self.editor.current_id]
        self.editor.current_id = self.settings.regions[0].id if self.settings.regions else None
        self._refresh_list(); self._changed()

    def _refresh_list(self):
        self._syncing = True
        self.region_list.clear()
        for region in self.settings.regions:
            item = QListWidgetItem(region.name)
            item.setData(Qt.ItemDataRole.UserRole, region.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if region.enabled else Qt.CheckState.Unchecked)
            self.region_list.addItem(item)
        row = next((index for index, region in enumerate(self.settings.regions) if region.id == self.editor.current_id), 0)
        if self.settings.regions:
            self.region_list.setCurrentRow(row)
        self._syncing = False
        self._set_controls_enabled(bool(self.settings.regions))

    def _select_row(self, row):
        if row < 0 or row >= len(self.settings.regions):
            self.editor.current_id = None
        else:
            self.editor.current_id = self.region_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.editor.update(); self._refresh_controls()
        if self.preview_only_box.isChecked():
            self._changed()

    def _item_enabled_changed(self, item):
        if self._syncing:
            return
        region = next((r for r in self.settings.regions if r.id == item.data(Qt.ItemDataRole.UserRole)), None)
        if region:
            region.enabled = item.checkState() == Qt.CheckState.Checked
            self._editor_changed()

    def _selected(self):
        return self.editor.region()

    def _refresh_controls(self):
        region = self._selected()
        self._set_controls_enabled(region is not None)
        if region is None:
            return
        self.angle_box.setEnabled(region.kind == "accessory")
        self.width_ratio_box.setEnabled(region.kind == "torso")
        self._syncing = True
        self.name_box.setEditText(region.name)
        self.kind_box.setCurrentIndex(self.kind_box.findData(region.kind))
        motion = region.motion
        self.amplitude_box.setValue(motion.amplitude_percent)
        self.angle_box.setValue(motion.angle_degrees)
        self.cycles_box.setValue(motion.cycles)
        self.phase_box.setValue(motion.phase_offset)
        self.lag_box.setValue(motion.tip_lag)
        self.bend_box.setValue(motion.bend_power)
        self.width_ratio_box.setValue(motion.width_ratio)
        self.lock_box.setValue(region.root_lock_percent)
        self.feather_box.setValue(region.feather_percent)
        self._syncing = False

    def _set_controls_enabled(self, enabled):
        for control in (self.name_box, self.kind_box, self.amplitude_box, self.angle_box, self.cycles_box,
                        self.phase_box, self.lag_box, self.bend_box, self.width_ratio_box,
                        self.lock_box, self.feather_box, self.root_button, self.tip_button):
            control.setEnabled(enabled)

    def _name_changed(self):
        if self._syncing:
            return
        region = self._selected()
        if region:
            region.name = self.name_box.currentText() or "部位"
            self._refresh_list(); self._changed()

    def _kind_changed(self, index):
        if self._syncing:
            return
        region = self._selected()
        if region:
            region.kind = self.kind_box.itemData(index)
            region.motion = defaults_for_kind(region.kind)
            region.root_lock_percent = {"hair": 12.0, "cloth": 18.0, "accessory": 5.0, "torso": 20.0}.get(region.kind, 12.0)
            self._changed()

    def _set_anchor(self, mode):
        if self._selected() is not None:
            self.editor.anchor_mode = mode
            self.editor.setCursor(Qt.CursorShape.CrossCursor)

    def _set_tool(self, tool):
        self.editor.tool = tool
        self.editor.anchor_mode = None

    def _motion_changed(self):
        if self._syncing:
            return
        region = self._selected()
        if region is None:
            return
        region.motion = PartMotion(
            self.amplitude_box.value(), self.angle_box.value(), self.cycles_box.value(),
            self.phase_box.value(), self.lag_box.value(), self.bend_box.value(), self.width_ratio_box.value())
        region.root_lock_percent = self.lock_box.value()
        region.feather_percent = self.feather_box.value()
        self._editor_changed()

    def reset_region(self):
        region = self._selected()
        if region is None:
            return
        region.motion = defaults_for_kind(region.kind)
        region.root_lock_percent = {"hair": 12.0, "cloth": 18.0, "accessory": 5.0, "torso": 20.0}.get(region.kind, 12.0)
        region.feather_percent = 8.0
        self._changed()

    def enlarge_editor(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("人物部位编辑 · 滚轮缩放 / 中键平移 / 0 归位 / Ctrl+Z 撤销")
        dialog.resize(1000, 800)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.tools_widget)
        layout.addWidget(self.editor, 1)
        anchors = QHBoxLayout()
        for label, mode in (("设置固定端", "root"), ("设置活动端", "tip")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, mode=mode: self._set_anchor(mode))
            anchors.addWidget(button)
        redo = QPushButton("重做")
        redo.clicked.connect(self.editor.undo_stack.redo)
        anchors.addWidget(redo)
        layout.addLayout(anchors)
        dialog.exec()
        self.layout().insertWidget(2, self.editor)
        self.layout().insertWidget(3, self.tools_widget)
        self.editor.show()
        self.tools_widget.show()
        self.preview.set_character_editing(False)
        dialog.deleteLater()
