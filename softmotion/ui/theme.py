from pathlib import Path


STYLE = """
QWidget { background: #111319; color: #d8ddeb; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; }
QLabel { background: transparent; }
QFrame#header { background: #171a23; border-bottom: 1px solid #282d3b; }
QLabel#title { font-size: 23px; font-weight: 700; color: #f0f2fa; }
QLabel#subtitle { color: #8390a7; font-size: 11px; }
QLabel#muted { color: #909bb1; font-size: 12px; }
QLabel#eyebrow { color: #8d9bb7; font-size: 11px; font-weight: 600; }
QLabel#section { color: #e1e6f3; font-size: 13px; font-weight: 600; padding-top: 5px; }
QLabel#badge { color: #b5bffd; background: #2b2d49; border: 1px solid #3b3f61; border-radius: 5px; padding: 3px 8px; font-size: 10px; }
QLabel#live { color: #91d4ba; background: #21382f; border-radius: 5px; padding: 4px 9px; font-size: 11px; }
QLabel#value { color: #c4cdf5; background: #272d3e; border-radius: 4px; padding: 2px 7px; font-family: 'Consolas'; font-size: 12px; }
QFrame#stage { background: #181c25; border: 1px solid #2b3141; border-radius: 12px; }
QWidget#stageBar { background: transparent; }
QFrame#transport { background: #1c212d; border: none; border-top: 1px solid #2b3141; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
QWidget#inspector { background: #191d27; }
QFrame#card { background: #212633; border: 1px solid #2e3547; border-radius: 8px; }
QLabel#hint { color: #9aa7c0; background: #20283a; border: 1px solid #2e3a53; border-radius: 7px; padding: 10px; font-size: 11px; }
QWidget#emptyState { background: transparent; }
QPushButton { background: #262d3d; color: #d8e0f2; border: 1px solid #3a4358; border-radius: 7px; padding: 9px 14px; font-weight: 500; }
QPushButton:hover { background: #333d53; border-color: #647199; }
QPushButton:pressed { background: #202738; }
QPushButton:focus { border-color: #939cff; }
QPushButton#primary { background: #7d83f5; color: #101321; border: 1px solid #9197ff; font-weight: 600; }
QPushButton#primary:hover { background: #999eff; border-color: #b0b5ff; }
QPushButton#primary:pressed { background: #6a72df; }
QPushButton#quiet { background: transparent; border-color: transparent; color: #a9b6cf; }
QPushButton#quiet:hover { background: #2a3245; border-color: #3a4358; }
QPushButton:disabled, QPushButton#primary:disabled { background: #212633; color: #647089; border-color: #2d3547; }
QSlider { background: transparent; min-height: 18px; }
QSlider::groove:horizontal { height: 4px; background: #343c50; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #8e98f5; border-radius: 2px; }
QSlider::handle:horizontal { background: #d1d6ff; border: 2px solid #8b94ec; width: 10px; height: 10px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #ffffff; border-color: #a7b1ff; }
QComboBox, QSpinBox { background: #242b3a; color: #dce3f5; border: 1px solid #3a4358; border-radius: 6px; padding: 7px 9px; min-height: 18px; selection-background-color: #4e5984; }
QComboBox:hover, QSpinBox:hover { border-color: #68769b; }
QComboBox:focus, QSpinBox:focus { border-color: #939cff; }
QComboBox::drop-down { width: 24px; border: none; }
QComboBox QAbstractItemView { background: #262d3d; selection-background-color: #444d78; color: #e1e7f5; border: 1px solid #566284; padding: 5px; }
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: #30394c; }
QCheckBox { background: transparent; spacing: 8px; color: #c1cbe0; font-size: 12px; padding: 3px 0; }
QCheckBox::indicator { width: 15px; height: 15px; }
QTabWidget::pane { background: #191d27; border: 1px solid #2e3547; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }
QTabBar::tab { background: #181c26; color: #8997b2; padding: 13px 23px; border-bottom: 2px solid #2c3344; }
QTabBar::tab:selected { background: #252b3b; color: #d6ddff; border-bottom: 2px solid #929cfa; }
QTabBar::tab:hover { color: #e0e7ff; }
QScrollArea { background: #191d27; border: none; }
QScrollBar:vertical { background: #191d27; width: 7px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #434e67; min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #657496; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QStatusBar { background: #151820; color: #7f8da7; border-top: 1px solid #252c3b; font-size: 11px; }
QStatusBar::item { border: none; }
QToolTip { background: #2a3348; color: #e2e8f5; border: 1px solid #637499; padding: 6px; }
QDialog, QMessageBox { background: #191e29; }
QProgressBar { background: #252d3f; border: none; border-radius: 5px; text-align: center; min-height: 12px; }
QProgressBar::chunk { background: #8c95f7; border-radius: 5px; }
"""

_ASSETS = (Path(__file__).parent / "assets").as_posix()
STYLE += f'''
QComboBox::down-arrow {{ image: url("{_ASSETS}/chevron-down.svg"); width: 12px; height: 12px; }}
QSpinBox::up-arrow {{ image: url("{_ASSETS}/chevron-up.svg"); width: 12px; height: 12px; }}
QSpinBox::down-arrow {{ image: url("{_ASSETS}/chevron-down.svg"); width: 12px; height: 12px; }}
QCheckBox::indicator {{ background: #272f42; border: 1px solid #55617f; border-radius: 4px; }}
QCheckBox::indicator:checked {{ background: #9ca6ff; border-color: #aeb7ff; image: url("{_ASSETS}/check.svg"); }}
'''
