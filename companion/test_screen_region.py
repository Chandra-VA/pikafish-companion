"""Screen-source isolation, physical coordinates, and stale-frame regressions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from capture import region_from_grid, validate_rect
from controller import Controller
from vision import Geometry, START, Recognizer


class RegionTests(unittest.TestCase):
    bounds = (-1920, 0, 1920, 1080)

    def setUp(self):
        self.app = Controller(diagnostics=False)
        self.search = patch.object(self.app, "start_analysis")
        self.search.start()
        self.bounds_patch = patch("capture.desktop_rect", return_value=self.bounds)
        self.bounds_patch.start()

    def tearDown(self):
        self.app.close()
        self.search.stop()
        self.bounds_patch.stop()

    def select(self):
        selection = region_from_grid((-1600, 100, -1040, 730), self.bounds)
        self.app.set_screen_region(selection)
        return selection

    def test_negative_monitor_origin_and_edge_piece_margin(self):
        selected = self.select()
        rect = selected["rect"]
        geo = Geometry(**selected["geometry"])
        self.assertLess(rect[0], -1600)
        self.assertGreater(rect[2], -1040)
        self.assertEqual((rect[0]+geo.left, rect[1]+geo.top), (-1600, 100))
        self.assertEqual((rect[0]+geo.right, rect[1]+geo.bottom), (-1040, 730))
        geo.validate((rect[2]-rect[0], rect[3]-rect[1]))
        for invalid in ((0,0,9999,9999), (0,0,0,10), (0,0,100,100), (0,0,800,100)):
            with self.assertRaises(ValueError):
                region_from_grid(invalid, self.bounds)
        with self.assertRaises(ValueError):
            validate_rect((0,0,True,200), self.bounds)

    def test_window_disappears_without_resetting_region(self):
        self.select()
        self.app.board = self.app.stable_board = deepcopy(START)
        self.app.selected_hwnd = 123
        with patch("controller.list_game_windows", return_value=[]):
            self.app.refresh_windows()
        self.assertEqual(self.app.board, START)
        self.assertEqual(self.app.capture_mode, "region")

    def test_monitor_captures_region_without_window_lookup_or_board_locator(self):
        selection = self.select()
        image = Image.new("RGB", (639,709))
        def capture(rect):
            self.app.closed.set()
            self.assertEqual(rect, selection["rect"])
            return image
        with patch("controller.capture_rect", side_effect=capture), patch("controller.list_game_windows", return_value=[]), \
                patch("controller.capture_game") as game, patch.object(self.app, "accept_image") as accept:
            self.app.monitor_loop()
        game.assert_not_called()
        accept.assert_called_once_with(image, self.app.region_geometry, epoch=self.app.capture_epoch)

    def test_pause_and_resume_keep_region_and_discard_late_frame(self):
        self.select()
        old_epoch = self.app.capture_epoch
        self.app.board = self.app.stable_board = deepcopy(START)
        self.app.action("automatic", {"enabled": False})
        self.assertTrue(self.app.simulation_enabled)
        self.app.action("automatic", {"enabled": True})
        self.assertEqual(self.app.capture_mode, "region")
        self.assertEqual(self.app.source, "屏幕区域")
        with patch.object(self.app.recognizer, "recognize") as recognize:
            self.app.accept_image(Image.new("RGB", (639,709)), self.app.region_geometry, epoch=old_epoch)
        recognize.assert_not_called()
        self.assertIsNone(self.app.board)

    def test_source_switch_during_recognition_cannot_overwrite_position(self):
        self.select()
        epoch = self.app.capture_epoch
        def changed(unused_image, unused_geometry):
            self.app.action("automatic", {"enabled": False})
            return deepcopy(START), [], [1]*90
        with patch.object(self.app.recognizer, "recognize", side_effect=changed):
            self.app.accept_image(Image.new("RGB", (639,709)), self.app.region_geometry, epoch=epoch)
        self.assertIsNone(self.app.board)

    def test_return_to_window_restores_original_template(self):
        self.select()
        self.app.windows = [(123, "天天象棋")]
        self.app.action("window", {"id":123})
        self.assertEqual(self.app.capture_mode, "window")
        self.assertIs(self.app.recognizer, self.app.window_recognizer)

    def test_learning_uses_corrected_pixels_and_separate_local_file(self):
        self.select()
        image = Image.new("RGB", (800,800), (220,175,110))
        draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=32)
        geometry = Geometry(80,90,640,720)
        for row in range(10):
            for col in range(9):
                piece = START[row][col]
                if piece != ".":
                    draw.text(geometry.screen_cell(row,col), piece.upper(), font=font, anchor="mm",
                              fill=(175,20,20) if piece.isupper() else (30,30,30))
        self.app.region_image, self.app.geometry = image, geometry
        self.app.board = self.app.stable_board = deepcopy(START)
        self.app.action("automatic", {"enabled":False})
        self.app.screen_recognizer = Recognizer()
        with tempfile.TemporaryDirectory() as folder, patch("controller.HERE", Path(folder)):
            self.app.learn_region()
            saved = Path(folder)/"screen-templates.npz"
            self.assertTrue(saved.exists())
            self.assertFalse((Path(folder)/"templates.npz").exists())
            recognized, uncertain, unused = Recognizer.load(saved).recognize(image, geometry)
            self.assertEqual(recognized, START)
            self.assertFalse(uncertain)
        self.assertFalse(self.app.simulation_enabled)


if __name__ == "__main__":
    unittest.main()
