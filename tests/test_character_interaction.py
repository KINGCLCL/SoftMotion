import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from softmotion.character.model import CharacterSettings, new_region
from softmotion.character.renderer import PreviewCharacterRenderer
from softmotion.ui.preview import Preview
from softmotion.ui.character_panel import CharacterPanel


class CharacterInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.image = QImage(600, 900, QImage.Format.Format_RGBA8888)
        self.image.fill(QColor('white'))
        self.settings = CharacterSettings(regions=[new_region(600, 900)])
        self.settings.regions[0].selection_mask[200:700, 150:450] = 255

    def test_proxy_preserves_source_coordinates_and_masks(self):
        renderer = PreviewCharacterRenderer()
        renderer.prepare(self.image, self.settings)
        self.assertEqual(max(renderer.image.width(), renderer.image.height()), 512)
        self.assertEqual(self.settings.regions[0].selection_mask.shape, (900, 600))
        self.assertEqual(renderer.render(self.image, .25).size(), self.image.size())
        self.assertEqual(renderer.render(self.image, .25).cacheKey(), renderer.cached.cacheKey())
        self.assertEqual(renderer.render(self.image, 0), renderer.render(self.image, 1))

    def test_parameter_changes_are_coalesced_and_edits_defer_preparation(self):
        preview = Preview()
        preview.set_image(self.image)
        preview.pause()
        try:
            with patch.object(preview.character_renderer, 'prepare', wraps=preview.character_renderer.prepare) as prepare:
                for value in range(10):
                    self.settings.regions[0].motion.amplitude_percent = value
                    preview.set_character_settings(self.settings)
                self.assertEqual(prepare.call_count, 0)
                QTest.qWait(100)
                self.assertEqual(prepare.call_count, 1)
                self.assertEqual(preview.character.regions[0].motion.amplitude_percent, 9)
                preview.set_character_editing(True)
                preview.set_character_settings(self.settings)
                QTest.qWait(100)
                self.assertEqual(prepare.call_count, 1)
                preview.set_character_editing(False)
                QTest.qWait(100)
                self.assertEqual(prepare.call_count, 2)
        finally:
            preview.close()

    def test_protection_erase_undo_and_reopen_clear_history(self):
        preview = Preview()
        panel = CharacterPanel(preview)
        panel.set_image(self.image)
        panel.add_region()
        editor = panel.editor
        panel.show()
        self.app.processEvents()
        point = editor.image_rect().center().toPoint()
        try:
            panel._set_tool('protect')
            QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=point)
            coverage = editor.settings.protection_mask.sum()
            self.assertGreater(coverage, 0)
            panel._set_tool('protect_erase')
            QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(editor.settings.protection_mask.sum(), 0)
            editor.undo_stack.undo()
            self.assertEqual(editor.settings.protection_mask.sum(), coverage)
            self.assertFalse(preview.editing_character)
            panel.set_image(self.image)
            self.assertFalse(editor.undo_stack.canUndo())
        finally:
            panel.close()
            preview.close()

    def test_enlarged_editor_returns_to_panel(self):
        preview = Preview()
        panel = CharacterPanel(preview)
        panel.set_image(self.image)
        panel.add_region()
        with patch('softmotion.ui.character_panel.QDialog.exec', return_value=0):
            panel.enlarge_editor()
        self.assertIs(panel.editor.parentWidget(), panel)
        self.assertIs(panel.tools_widget.parentWidget(), panel)
        self.assertEqual(panel.layout().indexOf(panel.editor), 2)
        panel.close()
        preview.close()


if __name__ == '__main__':
    unittest.main()
