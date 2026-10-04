"""Regressions for automatic side inference, variations and the loopback UI API."""
from copy import deepcopy
import io
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from PIL import Image
from controller import Controller
from engine import analyze, parse_info, EXE, NET
from vision import REFERENCE, REFERENCE_GEOMETRY, Geometry, to_fen
from variation import replay, evaluation
from web_app import make_server

HERE = Path(__file__).resolve().parent


class AnalysisTests(unittest.TestCase):
    @unittest.skipUnless(EXE.is_file() and NET.is_file(), "需要用户自行安装的 Pikafish 引擎和 NNUE")
    def test_live_engine_returns_multiple_replayable_lines(self):
        infos = {}
        def callback(line):
            info = parse_info(line)
            if info and not info.get("bound"):
                infos[info["rank"]] = info
        best = analyze(to_fen(REFERENCE, "w"), 1, callback=callback, multipv=3)
        self.assertEqual(set(infos), {1, 2, 3})
        self.assertEqual(infos[1]["moves"][0], best)
        self.assertGreaterEqual(len(infos[1]["moves"]), 4)
        for info in infos.values():
            positions, descriptions = replay(REFERENCE, info["moves"], "w")
            self.assertEqual(len(positions), len(info["moves"])+1)
            self.assertEqual(len(descriptions), len(info["moves"]))
            for index, description in enumerate(descriptions):
                self.assertTrue(description.startswith("红方" if index % 2 == 0 else "黑方"))

    def test_score_perspective_and_bounds(self):
        info = parse_info("info depth 18 multipv 2 score cp 250 lowerbound nodes 900 pv c2e3 a9a8")
        self.assertEqual(info["rank"], 2)
        self.assertIn("红分 ≥+250", evaluation(info, "w"))
        self.assertIn("红分 ≤-250", evaluation(info, "b"))
        self.assertIn("黑方占优", evaluation(info, "b"))
        self.assertIsNone(parse_info("info depth 4 score cp 12"))
        with self.assertRaises(ValueError):
            replay(REFERENCE, ["a9a8"], "w")


@unittest.skipUnless(all((HERE / name).is_file() for name in
    ("reference-board.png", "regression-board.png", "templates.npz")), "私人截图回归素材不随源码分发")
class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.app = Controller(diagnostics=False)
        self.stub = patch.object(self.app, "start_analysis")
        self.search = self.stub.start()
        self.image = Image.open(HERE / "reference-board.png").convert("RGB")

    def tearDown(self):
        self.stub.stop()
        self.app.close()

    def test_first_snapshot_does_not_guess_side(self):
        self.app.accept_image(self.image)
        self.assertIsNone(self.app.stable_board)
        self.app.accept_image(self.image)
        self.assertEqual(self.app.stable_board, REFERENCE)
        self.assertIsNone(self.app.turn)
        self.assertIn("分别分析红黑", self.app.turn_reason)
        self.search.assert_called_once()

    def test_red_on_top_is_normalized_automatically(self):
        self.app.accept_image(Image.open(HERE / "regression-board.png"), stable=True)
        self.assertFalse(self.app.geometry.red_bottom)
        self.assertEqual(self.app.board[9], list(".RB.KAB.."))
        self.assertIsNone(self.app.turn)

    def test_observed_move_automatically_sets_next_side(self):
        self.app.accept_image(self.image, stable=True)
        image = self.image.copy()
        image.paste(self.image.crop((331, 683, 388, 740)), (458, 619))
        image.paste(self.image.crop((395, 747, 452, 804)), (331, 683))
        self.app.accept_image(image, Geometry(*REFERENCE_GEOMETRY), stable=True)
        self.assertEqual(self.app.turn, "b")
        self.assertEqual(self.app.moves, ["c2e3"])
        self.assertEqual(len(self.app.history), 2)

    def test_invalid_board_still_has_readable_status(self):
        self.app.board = deepcopy(REFERENCE)
        self.app.board[9][4] = "."
        self.assertIsNone(self.app.snapshot()["fen"])

    def test_old_capture_is_ignored_after_source_switch(self):
        self.app.selected_hwnd = 123
        old_epoch = self.app.capture_epoch
        self.app.reset_position()
        self.app.accept_image(self.image, stable=True, hwnd=123, epoch=old_epoch)
        self.assertIsNone(self.app.board)


class ApiTests(unittest.TestCase):
    def test_local_http_auth_and_assets(self):
        app = Controller(diagnostics=False)
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            html = urllib.request.urlopen(base).read().decode()
            token = html.split('name="pika-token" content="', 1)[1].split('"', 1)[0]
            self.assertIn("后续变化", html)
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(base+"/api/state")
            self.assertEqual(missing.exception.code, 403)
            request = urllib.request.Request(base+"/api/state", headers={"X-Pika-Token": token})
            self.assertEqual(json.load(urllib.request.urlopen(request))["turn_mode"], "auto")
            foreign = urllib.request.Request(base+"/api/state", headers={"X-Pika-Token": token, "Origin": "https://example.com"})
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(foreign)
            self.assertEqual(rejected.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            app.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
