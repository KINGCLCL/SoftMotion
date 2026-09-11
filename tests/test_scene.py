from pathlib import Path
import tempfile
import unittest

import imageio_ffmpeg
import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from softmotion.exporting.encoder import ExportOptions, export_animation, render_frame
from softmotion.imaging.scene import SceneSettings
from softmotion.motion.effects import MotionSettings, PRESETS, sample_pose
from softmotion.ui.main_window import MainWindow


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = QImage(80, 100, QImage.Format.Format_RGBA8888)
        self.source.fill(QColor(240, 70, 40, 200))
        self.scene = SceneSettings(128, 160, crop=(0, 0, 80, 100))
        self.motion = MotionSettings(0, 0, 0, 2, 2, 5, 0, True)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, phase=0, scene=None):
        scene = scene or self.scene
        size = (scene.width, scene.height)
        return render_frame(self.source, size, size, phase, self.motion,
                            scene.background_mode == "transparent", scene)

    def export(self, kind, **kwargs):
        target = self.folder / ("frames" if kind == "png" else f"scene.{kind}")
        export_animation(self.source, (self.scene.width, self.scene.height), self.motion,
                         ExportOptions(kind, 160, 10, 1), target, scene=self.scene, **kwargs)
        return target

    def test_background_modes_and_crop(self):
        self.assertEqual(self.render().getpixel((0, 0))[3], 0)
        self.scene.background_mode = "solid"
        self.scene.background_color = "#12ab34"
        self.assertEqual(self.render().getpixel((0, 0)), (18, 171, 52, 255))
        self.scene.background_mode = "image"
        self.scene.background_image = QImage(30, 10, QImage.Format.Format_RGBA8888)
        self.scene.background_image.fill(QColor("#3344cc"))
        self.assertEqual(self.render().getpixel((0, 0)), (51, 68, 204, 255))
        # Crop only the green half: no red pixels should remain in the artwork.
        for y in range(100):
            for x in range(40, 80):
                self.source.setPixelColor(x, y, QColor("green"))
        self.scene.crop = (40, 0, 40, 100)
        self.assertEqual(self.render().getpixel((64, 80)), (0, 128, 0, 255))

    def test_fade_preserves_source_alpha_and_background(self):
        self.motion = MotionSettings(0, 0, 0, fade_percent=100)
        self.assertEqual(self.render(0).getpixel((64, 80))[3], 200)
        self.assertAlmostEqual(self.render(0.25).getpixel((64, 80))[3], 100, delta=1)
        self.assertEqual(self.render(0.5).getpixel((64, 80))[3], 0)
        self.assertEqual(self.render(0).tobytes(), self.render(1).tobytes())
        self.assertEqual(self.source.pixelColor(40, 50).alpha(), 200)
        for mode in ("solid", "image"):
            self.scene.background_mode = mode
            self.scene.background_color = "#3344cc"
            self.scene.background_image = QImage(30, 10, QImage.Format.Format_RGBA8888)
            self.scene.background_image.fill(QColor("#3344cc"))
            frame = self.render(0.5)
            self.assertEqual(frame.getpixel((64, 80)), (51, 68, 204, 255))
            self.assertEqual(frame.getpixel((0, 0)), (51, 68, 204, 255))

    def test_idle_feet_stay_grounded_and_cycles_do_not_drift(self):
        first = np.asarray(self.render(0))[:, :, 3]
        moved = np.asarray(self.render(0.25))[:, :, 3]
        self.assertEqual(np.where(first > 0)[0].max(), np.where(moved > 0)[0].max())
        self.assertFalse(np.array_equal(first, moved))
        for preset in PRESETS.values():
            for phase in (0, 0.125, 0.25, 0.75):
                self.assertEqual(sample_pose(phase, preset), sample_pose(phase + 1_000_000, preset))
        self.assertEqual(self.render(0).tobytes(), self.render(1).tobytes())

    def test_transparent_gif_disposal_has_no_trails(self):
        with Image.open(self.export("gif")) as gif:
            self.assertEqual(gif.size, (128, 160))
            self.assertEqual(gif.info["loop"], 0)
            self.assertEqual(gif.n_frames, 25)
            for index in range(gif.n_frames):
                gif.seek(index)
                actual = np.asarray(gif.convert("RGBA"))[:, :, 3] > 0
                expected = np.asarray(self.render(index / 25))[:, :, 3] >= 128
                self.assertTrue(np.array_equal(actual, expected), f"Transparent GIF frame {index} has a trail")

    def test_exact_png_dimensions_and_color_background(self):
        self.scene.width, self.scene.height = 129, 161
        self.scene.background_mode = "solid"
        self.scene.background_color = "#eecc11"
        path = self.export("png")
        with Image.open(path / "frame_00000.png") as frame:
            self.assertEqual(frame.size, (129, 161))
            self.assertEqual(frame.getpixel((0, 0)), (238, 204, 17, 255))

    def test_mp4_requires_explicit_matte_and_pads_odd_dimensions(self):
        with self.assertRaisesRegex(ValueError, "MP4"):
            self.export("mp4")
        self.scene.width, self.scene.height = 129, 161
        path = self.export("mp4", mp4_background="#20a040")
        decoder = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
        try:
            metadata = next(decoder)
            frames = list(decoder)
        finally:
            decoder.close()
        self.assertEqual(metadata["size"], (130, 162))
        self.assertEqual(len(frames), 25)
        pixel = np.frombuffer(frames[0], np.uint8)[:3].astype(int)
        self.assertLess(np.abs(pixel - [32, 160, 64]).max(), 8)

    def test_missing_background_invalid_crop_and_snapshot(self):
        snapshot = self.scene.snapshot()
        self.scene.width = 180
        self.assertEqual(snapshot.width, 128)
        self.scene.background_mode = "image"
        with self.assertRaisesRegex(ValueError, "背景图片"):
            self.export("png")
        self.scene.background_mode = "transparent"
        self.scene.crop = (70, 0, 80, 100)
        with self.assertRaisesRegex(ValueError, "裁剪"):
            self.export("png")

    def test_canvas_controls_crop_drag_and_preset_reset(self):
        window = MainWindow()
        window.show()
        try:
            window.preview.set_image(self.source)
            window.canvas_panel.set_source(self.source)
            panel = window.canvas_panel
            panel.width_box.setValue(256)
            panel.height_box.setValue(384)
            panel.set_crop((10, 20, 50, 60))
            self.assertEqual(window.preview.scene.crop, (10, 20, 50, 60))
            panel.crop_boxes[0].setValue(79)
            self.assertEqual(window.preview.scene.crop[2], 1)
            panel.reset_crop()
            self.assertEqual(window.preview.scene.crop, (0, 0, 80, 100))
            # Exercise the actual drag handler, including reverse drag and bounds.
            view = panel.crop_view
            view.resize(200, 150)
            rect = view.image_rect()
            start = QPoint(round(rect.left() + rect.width() * 0.8), round(rect.top() + rect.height() * 0.8))
            end = QPoint(round(rect.left() + rect.width() * 0.2), round(rect.top() + rect.height() * 0.2))
            QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=end)
            x, y, w, h = window.preview.scene.crop
            self.assertTrue(14 <= x <= 18 and 18 <= y <= 22)
            self.assertTrue(46 <= w <= 50 and 58 <= h <= 62)
            preset_box = window.motion_panel.preset_box
            preset_box.setCurrentIndex(preset_box.findData("人物 · 自然待机"))
            self.assertEqual(window.preview.settings, PRESETS["人物 · 自然待机"])
            scene = window.preview.scene.metadata()
            window.resize(900, 620)
            QTest.qWait(10)
            self.assertEqual(window.preview.scene.metadata(), scene)
            window.reset()
            self.assertEqual(window.preview.settings, MotionSettings())
            self.assertEqual(window.preview.scene.metadata(), scene)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
