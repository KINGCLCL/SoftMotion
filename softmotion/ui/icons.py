"""Small vector icons rendered by Qt; no external icon dependency."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


PATHS = {
    "wave": '<path d="M3 15C6 15 5 6 9 6s2 12 6 12 3-9 6-9"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.5"/><path d="m4 17 5-5 4 4 3-3 5 5"/>',
    "export": '<path d="M12 15V3m-4 4 4-4 4 4M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
    "play": '<path d="m8 5 11 7-11 7Z" fill="{color}" stroke-linejoin="round"/>',
    "pause": '<path d="M8 5v14M16 5v14" stroke-width="3"/>',
    "reset": '<path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/>',
    "canvas": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 1v6M16 17v6M1 16h6M17 8h6"/>',
}


def icon(name, color="#bac4db", size=20):
    body = PATHS[name].replace("{color}", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
