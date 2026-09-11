from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from softmotion.motion.effects import MotionSettings, PRESETS


class MotionPanel(QWidget):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.preview = preview
        self.setObjectName("inspector")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.preset_box = QComboBox()
        self.preset_box.addItem("自定义 Custom")
        for name, english in zip(PRESETS, ("Gentle Float", "Character · Natural Idle", "Character · Alert Idle", "Character · Tired Idle", "Fade Loop")):
            self.preset_box.addItem(f"{name} {english}", name)
        self.preset_box.setCurrentIndex(1)
        preset_title = QLabel("动态预设 Motion Presets")
        preset_title.setObjectName("eyebrow")
        layout.addWidget(preset_title)
        layout.addWidget(self.preset_box)
        self.sliders = {}
        self.defaults = {}
        self.divisors = {}
        defaults = MotionSettings()
        for name, label, maximum, divisor, unit in [
            ("float_px", "上下漂浮 Float", 120, 10, "px"),
            ("breath_percent", "整体缩放 Scale", 30, 10, "%"),
            ("sway_degrees", "左右摆动 Sway", 30, 10, "°"),
            ("fade_percent", "透明循环幅度 Fade", 100, 1, "%"),
            ("idle_breath_percent", "身体呼吸 Breathing", 30, 10, "%"),
            ("weight_shift_px", "重心转移 Weight Shift", 100, 10, "px"),
            ("lean_degrees", "身体倾斜 Lean", 200, 100, "°"),
            ("speed", "播放速度 Speed", 200, 100, "×"),
        ]:
            if name in {"float_px", "idle_breath_percent", "speed"}:
                heading = QLabel({"float_px": "基础运动 Basic Motion", "idle_breath_percent": "人物待机 Character Idle", "speed": "节奏 Timing"}[name])
                heading.setObjectName("section")
                layout.addWidget(heading)
                card = QFrame()
                card.setObjectName("card")
                group = QVBoxLayout(card)
                group.setContentsMargins(12, 10, 12, 10)
                group.setSpacing(4)
                layout.addWidget(card)
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            value_label = QLabel()
            value_label.setObjectName("value")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(value_label)
            group.addLayout(row)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(25 if name == "speed" else 0, maximum)
            slider.setAccessibleName(label)
            if name == "fade_percent":
                slider.setToolTip("0% 关闭；100% 完全淡出后淡入。循环速度由播放速度控制。\n0% disables fading; 100% fades out completely and back in. Speed controls the cycle.")
            default = round(getattr(defaults, name) * divisor)
            slider.setValue(default)

            def changed(value, key=name, divisor=divisor, unit=unit, output=value_label):
                number = value / divisor
                output.setText(f"{number:.2f}{unit}" if divisor == 100 else f"{number:.1f}{unit}")
                self.preview.set_parameter(key, number)
                self.preset_box.blockSignals(True)
                self.preset_box.setCurrentIndex(0)
                self.preset_box.blockSignals(False)

            slider.valueChanged.connect(changed)
            changed(default)
            group.addWidget(slider)
            self.sliders[name] = slider
            self.defaults[name] = default
            self.divisors[name] = divisor
        self.anchor_box = QCheckBox("以素材底部中心为脚底支点\nAnchor feet at bottom center")
        self.anchor_box.toggled.connect(self.set_anchor)
        layout.addWidget(self.anchor_box)
        hint = QLabel("待机小提示 Idle Tips\n使用透明人物素材，裁掉脚底空白；关闭上下漂浮，可让站姿更稳定。 Use a transparent character image and crop empty space below the feet. Disable Float for a steadier stance.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        layout.addStretch()
        self.preset_box.setCurrentIndex(1)
        self.preset_box.currentIndexChanged.connect(lambda: self.apply_preset(self.preset_box.currentData()))

    def set_anchor(self, enabled):
        self.preview.set_parameter("anchor_feet", enabled)
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentIndex(0)
        self.preset_box.blockSignals(False)

    def apply_preset(self, name):
        if name not in PRESETS:
            return
        settings = PRESETS[name]
        self.sync(settings)
        self.preview.phase = 0.0
        self.preview.update()
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentIndex(self.preset_box.findData(name))
        self.preset_box.blockSignals(False)

    def sync(self, settings):
        for name, slider in self.sliders.items():
            slider.setValue(round(getattr(settings, name) * self.divisors[name]))
        self.anchor_box.setChecked(settings.anchor_feet)

    def reset(self):
        self.sync(MotionSettings())
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentIndex(1)
        self.preset_box.blockSignals(False)
