from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import imageio_ffmpeg
from PIL import Image
from PySide6.QtGui import QColor, QImage, QPainter

from softmotion.imaging.render import draw_artwork, draw_scene
from softmotion.motion.effects import MotionSettings


class ExportCancelled(Exception):
    pass


@dataclass(frozen=True)
class ExportOptions:
    format: str = "gif"
    long_edge: int = 768
    fps: int = 24
    cycles: int = 1

    def timing(self, settings):
        duration = self.cycles * 5.0 / settings.speed
        count = max(2, round(duration * self.fps))
        return duration, count, count / duration

    def size(self, viewport):
        factor = self.long_edge / max(viewport)
        # Even dimensions keep H.264/yuv420p compatible without encoder rescaling.
        return tuple(max(2, round(value * factor / 2) * 2) for value in viewport)


def render_frame(source, viewport, size, phase, settings, transparent, scene=None, mp4_background=None):
    canvas = QImage(*size, QImage.Format.Format_RGBA8888)
    if canvas.isNull():
        raise MemoryError("无法分配导出画布，请降低尺寸。")
    canvas.fill(QColor(mp4_background) if mp4_background is not None else
                QColor(0, 0, 0, 0) if transparent else
                QColor(scene.background_color if scene is not None else "#12151c"))
    painter = QPainter(canvas)
    try:
        if scene is not None:
            # Scene coordinates are output pixels. Odd MP4 edges are padded, not scaled.
            draw_scene(painter, source, scene, phase, settings, mp4_background)
        else:
            scale = min(size[0] / viewport[0], size[1] / viewport[1])
            painter.translate((size[0] - viewport[0] * scale) / 2,
                              (size[1] - viewport[1] * scale) / 2)
            painter.scale(scale, scale)
            draw_artwork(painter, source, viewport, phase, settings)
    finally:
        painter.end()
    return Image.frombytes("RGBA", size, bytes(canvas.constBits()),
                           "raw", "RGBA", canvas.bytesPerLine())


def export_animation(source, viewport, settings: MotionSettings, options: ExportOptions,
                     destination, progress=lambda value: None, cancelled=lambda: False,
                     scene=None, mp4_background=None):
    """Stage output next to the target; publish only after encoding succeeds.

    PNG directories must be new. File overwrite confirmation belongs to the UI.
    No QPixmap or GUI widgets are accessed from the export thread.
    """
    destination = Path(destination)
    if options.format not in {"gif", "mp4", "png"}:
        raise ValueError("不支持的导出格式。")
    if (source.isNull() or min(viewport) < 64 or not 64 <= options.long_edge <= 1920
            or not 10 <= options.fps <= 60 or not 1 <= options.cycles <= 3
            or not math.isfinite(settings.speed) or not 0.25 <= settings.speed <= 2):
        raise ValueError("无效的图片或导出参数。")
    if options.format == "png" and destination.exists():
        raise ValueError("PNG 序列需要一个新的文件夹，请更换名称。")
    size = options.size(viewport)
    if scene is not None:
        if not (64 <= scene.width <= 1920 and 64 <= scene.height <= 1920):
            raise ValueError("画布宽高需要在 64–1920 像素之间。")
        if scene.background_mode not in {"transparent", "solid", "image"}:
            raise ValueError("无效的背景类型。")
        if scene.background_mode == "image" and scene.background_image.isNull():
            raise ValueError("请先选择背景图片，或切换到透明 / 纯色背景。")
        if scene.crop is not None:
            x, y, w, h = scene.crop
            if x < 0 or y < 0 or w < 1 or h < 1 or x + w > source.width() or y + h > source.height():
                raise ValueError("裁剪区域超出图片范围。")
        viewport = (scene.width, scene.height)
        size = output_size(scene, options.format)
        if options.format == "mp4" and scene.background_mode == "transparent" and mp4_background is None:
            raise ValueError("MP4 不支持透明背景，请选择 MP4 填充颜色。")
    duration, count, actual_fps = options.timing(settings)
    if options.format == "gif" and size[0] * size[1] * count > 150_000_000:
        raise ValueError("GIF 帧数据较大，请降低尺寸、帧率或循环次数（建议 512 px / 15 fps）。")

    def check_cancelled():
        if cancelled():
            raise ExportCancelled()

    check_cancelled()
    with tempfile.TemporaryDirectory(prefix=".softmotion-", dir=destination.parent) as staging:
        stage = Path(staging)
        output = stage / ("frames" if options.format == "png" else f"animation.{options.format}")
        frames = []
        process = None
        errors = None
        if options.format == "png":
            output.mkdir()
        try:
            if options.format == "mp4":
                errors = (stage / "ffmpeg.log").open("w+b")
                command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                           "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                           f"{size[0]}x{size[1]}", "-r", f"{actual_fps:.10f}",
                           "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "medium",
                           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                           str(output)]
                process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                           stdout=subprocess.DEVNULL, stderr=errors,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            for index in range(count):
                check_cancelled()
                # Exclude the duplicated end frame for a continuous loop.
                transparent = scene.background_mode == "transparent" if scene is not None else options.format == "png"
                frame = render_frame(source, viewport, size, index * options.cycles / count,
                                     settings, transparent, scene, mp4_background if options.format == "mp4" else None)
                if options.format == "png":
                    frame.save(output / f"frame_{index:05d}.png")
                elif options.format == "gif":
                    frames.append(gif_frame(frame, transparent))
                else:
                    process.stdin.write(frame.convert("RGB").tobytes())
                progress(round((index + 1) / count * 90))
            check_cancelled()
            if options.format == "gif":
                # GIF uses centiseconds; distribute rounding to avoid duration drift.
                times = [round(i * duration * 100 / count) * 10 for i in range(count + 1)]
                frames[0].save(output, save_all=True, append_images=frames[1:], loop=0,
                               duration=[b - a for a, b in zip(times, times[1:])],
                               disposal=2, optimize=False)
            elif options.format == "mp4":
                process.stdin.close()
                while True:
                    check_cancelled()
                    try:
                        code = process.wait(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                if code != 0:
                    errors.seek(0)
                    raise RuntimeError("MP4 编码失败：" + errors.read().decode("utf-8", errors="replace")[-2000:])
                if not output.exists() or output.stat().st_size == 0:
                    raise RuntimeError("MP4 编码器未生成有效文件。")
            else:
                metadata = {"frames": count, "fps": actual_fps, "duration_seconds": duration,
                            "size": size, "cycles": options.cycles, "motion": asdict(settings),
                            "pattern": "frame_%05d.png", "alpha": transparent}
                if scene is not None:
                    metadata["scene"] = scene.metadata()
                (output / "sequence.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            check_cancelled()
            if options.format == "png":
                output.rename(destination)
            else:
                os.replace(output, destination)
            progress(100)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            if errors is not None:
                errors.close()
    return destination


def output_size(scene, format):
    if format == "mp4":
        return scene.width + scene.width % 2, scene.height + scene.height % 2
    return scene.width, scene.height


def gif_frame(frame, transparent):
    if not transparent:
        return frame.convert("RGB").quantize(colors=256)
    palette_frame = frame.convert("RGB").quantize(colors=255)
    palette = palette_frame.getpalette()[:765]
    palette_frame.putpalette(palette + [0] * (768 - len(palette)))
    mask = frame.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
    palette_frame.paste(255, mask=mask)
    palette_frame.info["transparency"] = 255
    palette_frame.info["background"] = 255
    return palette_frame
