"""Core controller behavior without private screenshots or a downloaded engine."""
from copy import deepcopy
from pathlib import Path
import tempfile
import io
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from controller import Controller
from vision import REFERENCE, START, Geometry, Recognizer
from calibrate import main as calibrate

class PortableTests(unittest.TestCase):
    def test_calibration_cli_roundtrip_on_self_generated_board(self):
        image = Image.new("RGB", (800,800), (220,175,110))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=32)
        geometry = Geometry(80,90,640,720)
        for row in range(10):
            for col in range(9):
                piece = START[row][col]
                if piece != ".":
                    x,y = geometry.screen_cell(row,col)
                    draw.text((x,y),piece.upper(),font=font,anchor="mm",
                              fill=(175,20,20) if piece.isupper() else (30,30,30))
        with tempfile.TemporaryDirectory() as folder:
            source,output = Path(folder)/"own-board.png",Path(folder)/"templates.npz"
            image.save(source)
            console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
            with patch("sys.argv", ["calibrate",str(source),"--corners","80","90","640","720","--output",str(output)]), patch("sys.stdout", console):
                calibrate()
                console.flush()
                self.assertIn("已生成本机模板", console.buffer.getvalue().decode("utf-8"))
            board,uncertain,_ = Recognizer.load(output).recognize(image,geometry)
            self.assertEqual(board, START)
            self.assertEqual(uncertain, [])

    def test_missing_private_templates_does_not_prevent_ui_startup(self):
        with tempfile.TemporaryDirectory() as folder, patch("controller.HERE", Path(folder)):
            app = Controller(diagnostics=False)
            try:
                self.assertIsNone(app.recognizer.masks)
                self.assertIsNone(app.snapshot()["board"])
            finally:
                app.close()

    def test_stability_and_turn_detection_without_private_images(self):
        app = Controller(diagnostics=False)
        image = Image.new("RGB", (1000,1000), "white")
        geometry = Geometry(231,263,741,839)
        with patch.object(app,"start_analysis"), patch.object(app.recognizer,"recognize") as recognize:
            try:
                recognize.return_value = (deepcopy(REFERENCE), [], [1]*90)
                app.accept_image(image, geometry)
                self.assertIsNone(app.stable_board)
                app.accept_image(image, geometry)
                self.assertEqual(app.stable_board, REFERENCE)
                self.assertIsNone(app.turn)
                moved = deepcopy(REFERENCE)
                moved[7][2],moved[6][4] = ".","N"
                recognize.return_value = (moved, [], [1]*90)
                app.accept_image(image, geometry, stable=True)
                self.assertEqual(app.turn, "b")
                self.assertEqual(app.moves, ["c2e3"])
            finally:
                app.close()
