"""Classical grid registration and matching on independently degraded frames."""
from dataclasses import asdict
import io
import json
from pathlib import Path
import unittest
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from vision import Geometry, Recognizer, START, refine_grid

HERE = Path(__file__).resolve().parent


class GridTests(unittest.TestCase):
    def test_grid_fits_offsets_and_rejects_an_occluded_line(self):
        image = Image.new("RGB", (800,800), (225,190,140))
        draw = ImageDraw.Draw(image)
        expected = Geometry(80,90,640,720)
        for col in range(9):
            x = 80+col*70
            draw.line((x,90,x,720), fill=(140,110,80), width=2)
        for row in range(10):
            y = 90+row*70
            draw.line((80,y,640,y), fill=(140,110,80), width=2)
        # Simulate an overlay corrupting one vertical line.
        draw.rectangle((355,90,370,720), fill=(225,190,140))
        fitted = refine_grid(image, Geometry(74,83,637,718))
        for field in ("left","right","top","bottom"):
            self.assertLess(abs(getattr(fitted,field)-getattr(expected,field)), 2)

    def test_uniform_frame_does_not_invent_a_grid(self):
        geometry = Geometry(80,90,640,720)
        fitted = refine_grid(Image.new("RGB",(800,800),"white"),geometry)
        self.assertEqual(asdict(fitted), asdict(geometry))

    def test_light_blur_and_compression_preserve_piece_classes(self):
        image = Image.new("RGB", (800,800), (220,175,110))
        draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=32)
        geo = Geometry(80,90,640,720)
        for row in range(10):
            for col in range(9):
                piece = START[row][col]
                if piece != ".":
                    draw.text(geo.screen_cell(row,col),piece.upper(),font=font,anchor="mm",
                              fill=(175,20,20) if piece.isupper() else (30,30,30))
        recognizer = Recognizer()
        recognizer.calibrate(image,geo)
        buffer = io.BytesIO()
        image.filter(ImageFilter.GaussianBlur(.45)).save(buffer,format="JPEG",quality=65)
        altered = Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")
        board,uncertain,unused = recognizer.recognize(altered,geo)
        self.assertEqual(board,START)
        self.assertFalse(uncertain)
        # Cached, deduplicated templates cannot alter a subsequent result.
        self.assertEqual(recognizer.recognize(altered,geo)[0],START)


@unittest.skipUnless(all((HERE/name).is_file() for name in
    ("live-regression.png","live-regression-geometry.json","screen-templates.npz")),
    "本机直播截图与皮肤模板不随源码分发")
class LiveFrameTests(unittest.TestCase):
    def test_frame_not_used_to_create_the_templates(self):
        fixture = json.loads((HERE/"live-regression-geometry.json").read_text(encoding="utf-8"))
        image = Image.open(HERE/"live-regression.png").convert("RGB")
        recognizer = Recognizer.load(HERE/"screen-templates.npz")
        geometry = Geometry(**fixture["geometry"])
        for compression in (None,85,65):
            frame = image
            if compression:
                encoded=io.BytesIO()
                image.filter(ImageFilter.GaussianBlur(.35)).save(encoded,format="JPEG",quality=compression)
                frame=Image.open(io.BytesIO(encoded.getvalue())).convert("RGB")
            board,uncertain,unused=recognizer.recognize(frame,refine_grid(frame,geometry))
            if compression == 65:
                mismatches = [(r,c) for r in range(10) for c in range(9)
                              if board[r][c] != fixture["board"][r][c]]
                self.assertTrue(all(cell in uncertain for cell in mismatches))
            else:
                self.assertEqual(board,fixture["board"])
                self.assertFalse(uncertain)


if __name__ == "__main__":
    unittest.main()
