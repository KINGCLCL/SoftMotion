from pathlib import Path
import tempfile
import unittest
import json

import numpy as np
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from softmotion.character.model import CharacterRegion, CharacterSettings, PartMotion, Point
from softmotion.character.project import load_project, save_project
from softmotion.character.renderer import CharacterRenderer
from softmotion.character.warp import qimage_to_rgba
from softmotion.exporting.encoder import ExportOptions, export_animation, render_frame
from softmotion.imaging.scene import SceneSettings
from softmotion.motion.effects import MotionSettings


class CharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.source = QImage(96, 128, QImage.Format.Format_RGBA8888)
        for y in range(self.source.height()):
            for x in range(self.source.width()):
                self.source.setPixelColor(x, y, QColor(x * 2 % 255, y * 2 % 255, 80, 255))
        mask = np.zeros((128, 96), dtype=np.uint8)
        mask[16:108, 22:74] = 255
        self.region = CharacterRegion(
            name="前发", kind="hair", selection_mask=mask,
            root=Point(48, 18), tip=Point(72, 106),
            motion=PartMotion(amplitude_percent=18, tip_lag=0.12),
        )
        self.character = CharacterSettings(regions=[self.region])

    def test_region_moves_from_original_and_loops(self):
        renderer = CharacterRenderer(self.source, self.character)
        first = qimage_to_rgba(renderer.render(self.source, 0))
        moved = qimage_to_rgba(renderer.render(self.source, 0.25))
        end = qimage_to_rgba(renderer.render(self.source, 1))
        self.assertFalse(np.array_equal(first, moved))
        self.assertTrue(np.array_equal(first, end))
        # A point far outside the selected region remains source-identical.
        self.assertTrue(np.array_equal(first[0, 0], moved[0, 0]))

    def test_each_specialized_region_model_can_move(self):
        for kind in ("hair", "cloth", "accessory", "torso"):
            with self.subTest(kind=kind):
                region = self.region.snapshot()
                region.kind = kind
                region.motion = PartMotion(amplitude_percent=8, angle_degrees=8, width_ratio=0.4)
                renderer = CharacterRenderer(self.source, CharacterSettings(regions=[region]))
                neutral = qimage_to_rgba(renderer.render(self.source, 0))
                moved = qimage_to_rgba(renderer.render(self.source, 0.25))
                self.assertFalse(np.array_equal(neutral, moved))

    def test_export_renderer_uses_same_character_frame(self):
        first = render_frame(self.source, (160, 180), (160, 180), 0,
                             MotionSettings(), True, character=self.character)
        moved = render_frame(self.source, (160, 180), (160, 180), 0.25,
                             MotionSettings(), True, character=self.character)
        end = render_frame(self.source, (160, 180), (160, 180), 1,
                           MotionSettings(), True, character=self.character)
        self.assertNotEqual(first.tobytes(), moved.tobytes())
        self.assertEqual(first.tobytes(), end.tobytes())

    def test_png_export_includes_character_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "frames"
            export_animation(self.source, (160, 180), MotionSettings(),
                             ExportOptions("png", 128, 10, 1), destination,
                             character=self.character)
            metadata = json.loads((destination / "sequence.json").read_text())
            self.assertEqual(metadata["character"]["regions"][0]["name"], "前发")

    def test_protection_and_snapshot_are_independent(self):
        self.character.protection_mask = np.zeros((128, 96), dtype=np.uint8)
        self.character.protection_mask[40:80, 30:60] = 255
        clone = self.character.snapshot()
        clone.regions[0].selection_mask[20, 30] = 0
        clone.protection_mask[40, 30] = 0
        self.assertEqual(self.character.regions[0].selection_mask[20, 30], 255)
        self.assertEqual(self.character.protection_mask[40, 30], 255)

        renderer = CharacterRenderer(self.source, self.character)
        first = qimage_to_rgba(renderer.render(self.source, 0))
        moved = qimage_to_rgba(renderer.render(self.source, 0.25))
        self.assertTrue(np.array_equal(first[60, 45], moved[60, 45]))

    def test_invalid_coincident_control_points_are_rejected(self):
        region = self.region.snapshot()
        region.tip = region.root
        with self.assertRaises(ValueError):
            CharacterSettings(regions=[region]).validate(self.source.width(), self.source.height())

    def test_renderer_rejects_a_new_source_size(self):
        renderer = CharacterRenderer(self.source, self.character)
        resized = self.source.scaled(48, 64)
        with self.assertRaises(ValueError):
            renderer.render(resized, 0.25)

    def test_project_round_trip_preserves_masks_and_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "character.softmotion"
            save_project(path, self.source, "立绘.png", MotionSettings(speed=1.2),
                         SceneSettings(320, 400, crop=(2, 3, 80, 100)), self.character)
            loaded = load_project(path)
            self.assertEqual(loaded.source.size(), self.source.size())
            self.assertEqual(loaded.source_name, "立绘.png")
            self.assertEqual(loaded.scene.crop, (2, 3, 80, 100))
            self.assertEqual(loaded.motion.speed, 1.2)
            self.assertEqual(loaded.character.regions[0].name, "前发")
            self.assertTrue(np.array_equal(loaded.character.regions[0].selection_mask,
                                           self.region.selection_mask))

    def test_main_window_project_round_trip(self):
        from softmotion.ui.main_window import MainWindow
        window = MainWindow()
        try:
            window.preview.set_image(self.source)
            window.character_panel.set_image(self.source)
            window.character_panel.add_region()
            window.preview.scene.crop = (2, 3, 80, 100)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "window.softmotion"
                self.assertTrue(window.save_project(path))
                self.assertTrue(window.open_project(path))
                self.assertEqual(window.preview.scene.crop, (2, 3, 80, 100))
                self.assertEqual(len(window.preview.character.regions), 1)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
