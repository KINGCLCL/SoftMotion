"""SoftMotion V0.1 desktop entry point."""
import sys

from PySide6.QtWidgets import QApplication

from softmotion.ui.main_window import MainWindow
from softmotion.ui.theme import STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SoftMotion")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
