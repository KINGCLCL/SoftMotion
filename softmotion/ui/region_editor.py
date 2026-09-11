from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF, QUndoCommand, QUndoStack
from PySide6.QtWidgets import QWidget
import numpy as np

from softmotion.character.masks import paint_circle, paint_line
from softmotion.character.model import CharacterSettings
from softmotion.imaging.render import draw_checkerboard


def _mask_to_image(mask):
    mask = np.ascontiguousarray(mask, dtype=np.uint8)
    # DestinationIn uses the source alpha channel. A grayscale image is opaque
    # even when its pixel value is zero, so make the mask an explicit alpha image.
    rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    rgba[:, :, 3] = mask
    return QImage(rgba.data, mask.shape[1], mask.shape[0], rgba.strides[0], QImage.Format.Format_RGBA8888).copy()


class _MaskCommand(QUndoCommand):
    def __init__(self, editor, target, before, after):
        super().__init__("编辑部位蒙版 Edit region mask")
        self.editor, self.target = editor, target
        changed = np.argwhere(before != after)
        self.bbox = (0, 0, before.shape[0], before.shape[1]) if not changed.size else (
            int(changed[:, 0].min()), int(changed[:, 1].min()),
            int(changed[:, 0].max()) + 1, int(changed[:, 1].max()) + 1)
        y0, x0, y1, x1 = self.bbox
        self.before, self.after = before[y0:y1, x0:x1].copy(), after[y0:y1, x0:x1].copy()

    def undo(self):
        self.editor._apply_mask(self.target, self.before, self.bbox)

    def redo(self):
        self.editor._apply_mask(self.target, self.after, self.bbox)


class RegionEditor(QWidget):
    changed = Signal()
    point_changed = Signal()
    editing_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.settings = CharacterSettings()
        self.current_id = None
        self.tool = "brush"
        self.brush_radius = 18.0
        self.anchor_mode = None
        self.start = None
        self.lasso = []
        self.before_mask = None
        self.undo_stack = QUndoStack(self)
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.pan_start = None
        self.pan_origin = QPointF(0, 0)
        self.overlay_cache = {}
        self.cursor_position = None
        self.setMinimumHeight(300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_image(self, image):
        self.overlay_cache.clear()
        self.undo_stack.clear()
        self.start = self.last_point = self.before_mask = None
        self.current_id = None
        self.zoom = 1.0
        self.pan = QPointF()
        self.image = image.copy()
        self.settings.ensure_size(image.width(), image.height())
        self.update()

    def set_settings(self, settings):
        self.overlay_cache.clear()
        self.settings = settings
        if not self.image.isNull():
            self.settings.ensure_size(self.image.width(), self.image.height())
        self.update()

    def set_current(self, region_id):
        self.current_id = region_id
        self.update()

    def region(self):
        return next((item for item in self.settings.regions if item.id == self.current_id), None)

    def image_rect(self):
        if self.image.isNull():
            return QRectF()
        fit = min((self.width() - 16) / self.image.width(), (self.height() - 16) / self.image.height())
        fit *= self.zoom
        w, h = self.image.width() * fit, self.image.height() * fit
        return QRectF((self.width() - w) / 2 + self.pan.x(),
                      (self.height() - h) / 2 + self.pan.y(), w, h)

    def source_point(self, position):
        rect = self.image_rect()
        if rect.isNull():
            return None
        x = (position.x() - rect.x()) * self.image.width() / rect.width()
        y = (position.y() - rect.y()) * self.image.height() / rect.height()
        if not (0 <= x < self.image.width() and 0 <= y < self.image.height()):
            return None
        return x, y

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.image.isNull():
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             "导入图片后在这里圈选部位\nImport an image, then select a character part here")
            return
        rect = self.image_rect()
        draw_checkerboard(painter, rect.intersected(QRectF(self.rect())))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(rect, self.image)
        region = self.region()
        if region is not None:
            painter.drawImage(rect, self._overlay(region.id, region.selection_mask, (137, 149, 255, 85)))
        if self.settings.protection_mask is not None:
            painter.drawImage(rect, self._overlay("protection", self.settings.protection_mask, (255, 105, 105, 70)))
        painter.setPen(QColor("#a5b4ff"))
        region = self.region()
        if region is not None:
            for point, color in ((region.root, QColor("#8ff0c0")), (region.tip, QColor("#ffce75"))):
                p = QPointF(rect.x() + point.x * rect.width() / self.image.width(),
                            rect.y() + point.y * rect.height() / self.image.height())
                painter.setBrush(color)
                painter.drawEllipse(p, 5, 5)
        if self.cursor_position is not None and self.tool in {"brush", "erase", "protect", "protect_erase"}:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("white"))
            painter.drawEllipse(self.cursor_position, self.brush_radius, self.brush_radius)
        if self.lasso and self.tool == "ellipse":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(QPointF(*self.lasso[0]), QPointF(*self.lasso[-1])).normalized())
        elif self.lasso:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in self.lasso]))

    def _overlay(self, key, mask, color):
        if key not in self.overlay_cache:
            mask = np.ascontiguousarray(mask, dtype=np.uint8)
            overlay = QImage(mask.data, mask.shape[1], mask.shape[0], mask.strides[0], QImage.Format.Format_Indexed8).copy()
            r, g, b, alpha = color
            overlay.setColorTable([QColor(r, g, b, round(i * alpha / 255)).rgba() for i in range(256)])
            self.overlay_cache[key] = overlay
        return self.overlay_cache[key]

    def _apply_mask(self, target, value, bbox=None):
        self.overlay_cache.clear()
        if target == "protection":
            if self.settings.protection_mask is None:
                self.settings.protection_mask = np.zeros((self.image.height(), self.image.width()), dtype=np.uint8)
            target_mask = self.settings.protection_mask
        else:
            region = next((item for item in self.settings.regions if item.id == target), None)
            if region is None:
                return
            target_mask = region.selection_mask
        if bbox is None:
            target_mask[:] = value
        else:
            y0, x0, y1, x1 = bbox
            target_mask[y0:y1, x0:x1] = value
        self.settings.bump()
        self.changed.emit()
        self.update()

    def _start_edit(self):
        self.overlay_cache.clear()
        region = self.region()
        if self.tool in {"protect", "protect_erase"}:
            if self.settings.protection_mask is None:
                self.settings.protection_mask = np.zeros((self.image.height(), self.image.width()), dtype=np.uint8)
            self.before_mask = self.settings.protection_mask.copy()
            return
        if region is not None:
            self.before_mask = region.selection_mask.copy()

    def _mask_target(self):
        return "protection" if self.tool in {"protect", "protect_erase"} else self.current_id

    def _current_mask(self):
        if self.tool in {"protect", "protect_erase"}:
            if self.settings.protection_mask is None:
                self.settings.protection_mask = np.zeros((self.image.height(), self.image.width()), dtype=np.uint8)
            return self.settings.protection_mask
        region = self.region()
        return None if region is None else region.selection_mask

    def _commit_edit(self):
        if self.before_mask is None:
            return
        target = self._mask_target()
        after = self._current_mask()
        if target is not None and after is not None and not np.array_equal(self.before_mask, after):
            self.undo_stack.push(_MaskCommand(self, target, self.before_mask, after.copy()))
        self.before_mask = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.editing_changed.emit(True)
            self.pan_start = event.position()
            self.pan_origin = QPointF(self.pan)
            return
        if event.button() != Qt.MouseButton.LeftButton or self.image.isNull():
            return
        point = self.source_point(event.position())
        if point is None:
            return
        self.setFocus()
        if self.anchor_mode in {"root", "tip"}:
            region = self.region()
            if region is not None:
                from softmotion.character.model import Point
                other = region.tip if self.anchor_mode == "root" else region.root
                if np.hypot(point[0] - other.x, point[1] - other.y) <= 1e-6:
                    return
                if self.anchor_mode == "root":
                    region.root = Point(*point)
                else:
                    region.tip = Point(*point)
                self.anchor_mode = None
                self.settings.bump()
                self.point_changed.emit()
                self.changed.emit()
                self.update()
            return
        self.editing_changed.emit(True)
        self.start = point
        self._start_edit()
        if self.tool in {"lasso", "ellipse"}:
            self.lasso = [(self.image_rect().x() + point[0] * self.image_rect().width() / self.image.width(),
                           self.image_rect().y() + point[1] * self.image_rect().height() / self.image.height())]
        else:
            mask = self._current_mask()
            if mask is not None:
                value = 0 if self.tool in {"erase", "protect_erase"} else 255
                paint_circle(mask, point, self.brush_radius / max(1e-6, self.image_rect().width() / self.image.width()), value)
                self.update()

    def mouseMoveEvent(self, event):
        self.cursor_position = event.position()
        self.update()
        if self.pan_start is not None:
            delta = event.position() - self.pan_start
            self.pan = self.pan_origin + delta
            self.update()
            return
        point = self.source_point(event.position())
        if self.start is None or point is None:
            return
        if self.tool in {"lasso", "ellipse"}:
            rect = self.image_rect()
            self.lasso.append((rect.x() + point[0] * rect.width() / self.image.width(),
                               rect.y() + point[1] * rect.height() / self.image.height()))
            self.update()
            return
        mask = self._current_mask()
        if mask is None:
            return
        self.overlay_cache.clear()
        previous = getattr(self, "last_point", None) or self.start
        value = 0 if self.tool in {"erase", "protect_erase"} else 255
        radius = self.brush_radius / max(1e-6, self.image_rect().width() / self.image.width())
        paint_line(mask, previous, point, radius, value)
        self.last_point = point
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = None
            self.editing_changed.emit(False)
            return
        if self.start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.source_point(event.position()) or self.start
        if self.tool in {"lasso", "ellipse"}:
            mask = self._current_mask()
            if mask is not None:
                rect = self.image_rect()
                if self.tool == "lasso":
                    screen_point = (event.position().x(), event.position().y())
                    if not self.lasso or self.lasso[-1] != screen_point:
                        self.lasso.append(screen_point)
                temporary = QImage(self.image.size(), QImage.Format.Format_Grayscale8)
                temporary.fill(0)
                painter = QPainter(temporary)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255))
                if self.tool == "ellipse":
                    start = QPointF(*self.start)
                    end = QPointF(*point)
                    painter.drawEllipse(QRectF(start, end).normalized())
                else:
                    polygon = QPolygonF([QPointF((x - rect.x()) * self.image.width() / rect.width(),
                                                 (y - rect.y()) * self.image.height() / rect.height()) for x, y in self.lasso])
                    painter.drawPolygon(polygon)
                painter.end()
                edited = np.frombuffer(bytes(temporary.constBits()), dtype=np.uint8).reshape(temporary.height(), temporary.bytesPerLine())[:, :temporary.width()]
                if self.tool == "lasso" or self.tool == "ellipse":
                    mask[:] = np.maximum(mask, edited)
            self.lasso = []
            self._commit_edit()
        else:
            mask = self._current_mask()
            if mask is not None:
                previous = getattr(self, "last_point", None) or self.start
                value = 0 if self.tool in {"erase", "protect_erase"} else 255
                radius = self.brush_radius / max(1e-6, self.image_rect().width() / self.image.width())
                paint_line(mask, previous, point, radius, value)
            self._commit_edit()
        self.start = None
        self.last_point = None
        self.editing_changed.emit(False)
        self.update()

    def wheelEvent(self, event):
        if self.image.isNull():
            return
        cursor = event.position()
        source_point = self.source_point(cursor)
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = max(0.5, min(8.0, self.zoom * factor))
        if source_point is not None:
            rect = self.image_rect()
            projected = QPointF(rect.x() + source_point[0] * rect.width() / self.image.width(),
                                rect.y() + source_point[1] * rect.height() / self.image.height())
            self.pan += cursor - projected
        self.update()

    def leaveEvent(self, event):
        self.cursor_position = None
        self.update()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z:
            self.undo_stack.undo()
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Y:
            self.undo_stack.redo()
        elif event.key() == Qt.Key.Key_0:
            self.zoom = 1.0
            self.pan = QPointF()
            self.update()
        elif event.key() == Qt.Key.Key_Escape:
            self.anchor_mode = None
        else:
            super().keyPressEvent(event)
