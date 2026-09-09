import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import imageio_ffmpeg
import numpy as np
from PIL import Image
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from softmotion.exporting.encoder import ExportCancelled, ExportOptions, export_animation, render_frame
from softmotion.motion.effects import MotionSettings
from softmotion.ui.export_dialog import ExportDialog
from softmotion.ui.main_window import MainWindow


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = QImage(80, 60, QImage.Format.Format_RGBA8888)
        self.source.fill(QColor(220, 90, 40, 128))
        self.viewport = (400, 320)
        self.settings = MotionSettings(12, 3, 3, 2)

    def tearDown(self):
        self.temp.cleanup()

    def export(self, kind, path=None, **kwargs):
        path = path or self.folder / ("序列" if kind == "png" else f"动画.{kind}")
        export_animation(self.source, self.viewport, self.settings,
                         ExportOptions(kind, 128, 10, 1), path, **kwargs)
        return path

    def test_png_alpha_motion_and_metadata(self):
        path = self.export("png")
        frames = sorted(path.glob("*.png"))
        self.assertEqual(len(frames), 25)
        metadata = json.loads((path / "sequence.json").read_text())
        self.assertEqual(metadata["fps"], 10)
        self.assertEqual(metadata["duration_seconds"], 2.5)
        with Image.open(frames[0]) as first, Image.open(frames[6]) as moved:
            self.assertEqual(first.mode, "RGBA")
            self.assertEqual(first.getpixel((0, 0))[3], 0)
            self.assertEqual(first.getpixel((64, 51))[3], 128)
            self.assertNotEqual(first.tobytes(), moved.tobytes())
            expected = render_frame(self.source, self.viewport, first.size, 0, self.settings, True)
            self.assertEqual(first.tobytes(), expected.tobytes())
        with self.assertRaises(ValueError):
            self.export("png", path)

    def test_gif_loop_duration_and_background(self):
        path = self.export("gif")
        with Image.open(path) as animation:
            self.assertEqual(animation.info["loop"], 0)
            self.assertGreater(animation.n_frames, 1)
            self.assertEqual(animation.size, (128, 102))
            duration = 0
            for index in range(animation.n_frames):
                animation.seek(index)
                duration += animation.info["duration"]
                self.assertEqual(animation.convert("RGB").getpixel((0, 0)), (18, 21, 28))
            self.assertEqual(duration, 2500)

    def test_mp4_decodes_all_frames(self):
        path = self.export("mp4")
        decoder = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
        try:
            metadata = next(decoder)
            frames = list(decoder)
        finally:
            decoder.close()
        self.assertEqual(metadata["size"], (128, 102))
        self.assertAlmostEqual(metadata["duration"], 2.5, places=1)
        self.assertEqual(len(frames), 25)
        self.assertNotEqual(frames[0], frames[6])

    def test_cancel_preserves_files_and_cleans_staging(self):
        for kind in ("gif", "mp4", "png"):
            with self.subTest(kind=kind):
                path = self.folder / ("new_frames" if kind == "png" else f"existing.{kind}")
                if kind != "png":
                    path.write_bytes(b"keep existing content")
                state = [False]
                def progress(value):
                    state[0] = value > 10
                with self.assertRaises(ExportCancelled):
                    self.export(kind, path, progress=progress, cancelled=lambda: state[0])
                if kind == "png":
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(path.read_bytes(), b"keep existing content")
                self.assertEqual(list(self.folder.glob(".softmotion-*")), [])

    def test_encoder_error_preserves_destination(self):
        path = self.folder / "old.mp4"
        path.write_bytes(b"old")
        with patch("softmotion.exporting.encoder.imageio_ffmpeg.get_ffmpeg_exe", return_value="missing-ffmpeg.exe"):
            with self.assertRaises(OSError):
                self.export("mp4", path)
        self.assertEqual(path.read_bytes(), b"old")
        self.assertEqual(list(self.folder.glob(".softmotion-*")), [])

    def test_preview_matches_export(self):
        window = MainWindow()
        window.show()
        try:
            window.preview.set_image(self.source)
            window.preview.pause()
            window.preview.phase = 0.25
            window.preview.settings = self.settings
            QTest.qWait(20)
            preview = window.preview
            size = (preview.width() - 24, preview.height() - 24)
            preview.scene.width, preview.scene.height = size
            preview.scene.background_mode = "solid"
            expected = render_frame(self.source, size, size, 0.25, self.settings, False, preview.scene)
            grabbed = preview.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            if grabbed.size() == preview.size():
                interior = grabbed.copy(12, 12, *size)
                actual = np.frombuffer(interior.constBits(), np.uint8).reshape(size[1], size[0], 4)
                expected_array = np.asarray(expected)
                self.assertLessEqual(np.abs(actual[2:-2, 2:-2].astype(int) - expected_array[2:-2, 2:-2]).max(), 1)
        finally:
            window.close()

    def test_dialog_timing_and_background_details(self):
        dialog = ExportDialog(self.settings, self.viewport, "test.png")
        self.assertIn("2.50 秒", dialog.details.text())
        dialog.format_box.setCurrentIndex(2)
        self.assertIn("透明背景", dialog.details.text())
        dialog.cycles_box.setValue(2)
        self.assertIn("5.00 秒", dialog.details.text())
        dialog.close()

    def test_gui_background_export(self):
        window = MainWindow()
        window.show()
        window.preview.set_image(self.source)
        path = self.folder / "gui.gif"
        def accept_dialog(dialog):
            dialog.destination = path
            dialog.size_box.setCurrentIndex(0)
            dialog.fps_box.setCurrentIndex(0)
            return QDialog.DialogCode.Accepted
        try:
            with patch.object(ExportDialog, "exec", accept_dialog), patch(
                    "softmotion.ui.main_window.QMessageBox.information") as completed:
                window.choose_export()
                self.assertFalse(window.export_button.isEnabled())
                for _ in range(300):
                    QTest.qWait(20)
                    time.sleep(0.01)  # Let the Python worker acquire the GIL.
                    if window.export_worker is None:
                        break
                self.assertIsNone(window.export_worker)
                completed.assert_called_once()
                self.assertTrue(path.exists())
                self.assertTrue(window.export_button.isEnabled())
        finally:
            if window.export_worker is not None:
                window.export_worker.requestInterruption()
                window.export_worker.wait()
                self.app.processEvents()
            window.close()


if __name__ == "__main__":
    unittest.main()
