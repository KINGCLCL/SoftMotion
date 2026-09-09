import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from softmotion.imaging.loader import load_image
from softmotion.motion.effects import MotionSettings, sample_pose
from softmotion.ui.main_window import MainWindow
from softmotion.ui.theme import STYLE


class MotionTests(unittest.TestCase):
    def test_periodicity_and_bounds(self):
        settings = MotionSettings(12, 3, 3)
        for phase in (0, 0.125, 0.25, 0.5, 0.75, 0.875):
            pose = sample_pose(phase, settings)
            self.assertEqual(pose, sample_pose(phase + 1_000_000, settings))
            self.assertLessEqual(abs(pose.y), 12)
            self.assertTrue(0.97 <= pose.scale <= 1.03)
            self.assertLessEqual(abs(pose.rotation), 3)
        self.assertEqual(sample_pose(0, settings).scale, 1)

    def test_disabled_effects(self):
        pose = sample_pose(0.25, MotionSettings(0, 0, 0))
        self.assertEqual((pose.y, pose.scale, pose.rotation), (0, 1, 0))


class ImageAndGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_image(self, suffix):
        path = self.folder / f"测试素材.{suffix}"
        image = Image.new("RGBA", (320, 180), (123, 90, 200, 120))
        if suffix == "jpg":
            image = image.convert("RGB")
        image.save(path)
        return path

    def test_supported_formats_and_alpha(self):
        for suffix in ("png", "jpg", "webp"):
            with self.subTest(suffix=suffix):
                asset = load_image(self.make_image(suffix))
                self.assertEqual((asset.width, asset.height), (320, 180))
                self.assertEqual(asset.preview.pixelColor(0, 0).alpha(),
                                 255 if suffix == "jpg" else 120)

    def test_invalid_and_animated_images(self):
        bad = self.folder / "bad.png"
        bad.write_bytes(b"not an image")
        with self.assertRaises(ValueError):
            load_image(bad)
        with self.assertRaises(ValueError):
            load_image(self.folder / "absent.jpg")
        with self.assertRaises(ValueError):
            load_image(self.folder / "image.gif")
        animation = self.folder / "animation.webp"
        Image.new("RGB", (10, 10), "red").save(
            animation, save_all=True,
            append_images=[Image.new("RGB", (10, 10), "blue")], duration=100)
        with self.assertRaises(ValueError):
            load_image(animation)

    def test_preview_resize_and_orientation(self):
        path = self.folder / "large.png"
        Image.new("RGBA", (3000, 1000)).save(path)
        asset = load_image(path)
        self.assertEqual(asset.width, 3000)
        self.assertEqual(asset.preview.width(), 2048)
        oriented = self.folder / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (30, 20)).save(oriented, exif=exif)
        asset = load_image(oriented)
        self.assertEqual((asset.width, asset.height), (20, 30))

    def test_gui_play_pause_reset_and_error(self):
        window = MainWindow()
        window.show()
        try:
            self.assertFalse(window.play_button.isEnabled())
            self.assertTrue(window.open_image(self.make_image("png")))
            QTest.qWait(120)
            self.assertGreater(window.preview.phase, 0)
            window.pause_button.click()
            phase = window.preview.phase
            QTest.qWait(80)
            self.assertEqual(window.preview.phase, phase)
            window.sliders["speed"].setValue(200)
            self.assertEqual(window.preview.phase, phase)
            window.play_button.click()
            QTest.qWait(80)
            self.assertGreater(window.preview.phase, phase)
            self.assertFalse(window.play_button.isEnabled())
            window.sliders["float_px"].setValue(120)
            window.sliders["breath_percent"].setValue(30)
            window.sliders["sway_degrees"].setValue(30)
            window.resize(820, 560)
            QTest.qWait(40)
            self.assertFalse(window.grab().isNull())
            with patch("softmotion.ui.main_window.QMessageBox.warning") as warning:
                self.assertFalse(window.open_image(self.folder / "missing.png"))
                warning.assert_called_once()
                self.assertFalse(window.preview.pixmap.isNull())
            window.reset_button.click()
            self.assertFalse(window.preview.playing)
            self.assertEqual(window.preview.phase, 0)
            self.assertEqual(window.preview.settings, MotionSettings())
            for name, slider in window.sliders.items():
                self.assertEqual(slider.value(), window.defaults[name])
            # Confirm resumed motion remains time-based and speed changes continuous.
            with patch("softmotion.ui.preview.perf_counter", return_value=100):
                window.preview.play()
            with patch("softmotion.ui.preview.perf_counter", return_value=101):
                window.preview.set_parameter("speed", 2)
            self.assertTrue(math.isclose(window.preview.phase, 0.2))
            with patch("softmotion.ui.preview.perf_counter", return_value=102):
                window.preview.pause()
            self.assertTrue(math.isclose(window.preview.phase, 0.6))
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
