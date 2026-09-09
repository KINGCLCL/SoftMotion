"""Shared preview/export drawing, always based on the unmodified source image."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from softmotion.motion.effects import sample_pose


def draw_artwork(painter, image, viewport, phase, settings, crop=None):
    width, height = viewport
    source = QRectF(*crop) if crop is not None else QRectF(image.rect())
    margin = min(40, min(width, height) * 0.08)
    fit = min((width - 2 * margin) / source.width(),
              (height - 2 * margin) / source.height()) * 0.84
    w, h = source.width() * fit, source.height() * fit
    pose = sample_pose(phase, settings)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    foot_anchor = settings.anchor_feet
    painter.translate(width / 2, height / 2 + (h / 2 if foot_anchor else 0) + pose.y)
    painter.rotate(pose.rotation + pose.lean)
    painter.shear(-pose.weight_shift / h, 0)
    painter.scale(pose.scale * pose.stretch_x, pose.scale * pose.stretch_y)
    painter.drawImage(QRectF(-w / 2, -h if foot_anchor else -h / 2, w, h), image, source)
    painter.restore()


def draw_scene(painter, image, scene, phase, settings, mp4_background=None):
    """Draw actual output pixels; checkerboards and crop guides never enter exports."""
    canvas = QRectF(0, 0, scene.width, scene.height)
    painter.save()
    painter.setClipRect(canvas)
    if mp4_background is not None:
        painter.fillRect(canvas, QColor(mp4_background))
    if scene.background_mode in {"solid", "image"}:
        painter.fillRect(canvas, QColor(scene.background_color))
    if scene.background_mode == "image" and not scene.background_image.isNull():
        background = scene.background_image
        factor = max(scene.width / background.width(), scene.height / background.height())
        w, h = background.width() * factor, background.height() * factor
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF((scene.width - w) / 2, (scene.height - h) / 2, w, h), background)
    draw_artwork(painter, image, (scene.width, scene.height), phase, settings, scene.crop)
    painter.restore()


def draw_checkerboard(painter, rect):
    painter.save()
    painter.setClipRect(rect)
    painter.fillRect(rect, QColor("#252a34"))
    tile = 16
    for y in range(int(rect.top()), int(rect.bottom()) + 1, tile):
        for x in range(int(rect.left()), int(rect.right()) + 1, tile):
            if ((x - int(rect.left())) // tile + (y - int(rect.top())) // tile) % 2:
                painter.fillRect(x, y, tile, tile, QColor("#303743"))
    painter.restore()
