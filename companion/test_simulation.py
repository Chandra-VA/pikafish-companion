"""Legal local moves, practice history, per-move grading and safe live resumption."""
from copy import deepcopy
from pathlib import Path
import threading
import time
import unittest
import tempfile
import json
from unittest.mock import patch
from PIL import Image
from controller import Controller
from engine import analyze, EXE, NET
from grading import grade_move
from rules import apply_move, legal_moves, in_check
from vision import START, REFERENCE, to_fen
from web_app import restore_snapshot

HERE = Path(__file__).resolve().parent


class RuleTests(unittest.TestCase):
    def test_opening_perft_matches_real_engine_baseline(self):
        first = legal_moves(START, "w")
        self.assertEqual(len(first), 44)
        self.assertEqual(sum(len(legal_moves(apply_move(START, move, "w"), "b")) for move in first), 1920)

    def empty(self):
        board = [["."]*9 for _ in range(10)]
        board[0][4], board[9][4], board[5][4] = "k", "K", "P"
        return board

    def test_blocked_horse_and_elephant(self):
        board = self.empty()
        board[7][3], board[6][3] = "N", "P"
        with self.assertRaises(ValueError):
            apply_move(board, "d2c4", "w")
        board[9][2], board[8][3] = "B", "P"
        with self.assertRaises(ValueError):
            apply_move(board, "c0e2", "w")
        board[5][2] = "B"
        with self.assertRaises(ValueError):
            apply_move(board, "c4e6", "w")

    def test_cannon_requires_exactly_one_screen(self):
        board = self.empty()
        board[2][0], board[4][0] = "c", "P"
        with self.assertRaises(ValueError):
            apply_move(board, "a7a5", "b")
        board[3][0] = "p"
        position = apply_move(board, "a7a5", "b")
        self.assertEqual(position[4][0], "c")

    def test_kings_facing_and_ignoring_check_are_forbidden(self):
        board = self.empty()
        board[5][4] = "R"
        with self.assertRaises(ValueError):
            apply_move(board, "e4d4", "w")
        board = self.empty()
        board[9][0], board[8][4] = "r", "A"
        self.assertTrue(in_check(board, "w"))
        with self.assertRaises(ValueError):
            apply_move(board, "e1f2", "w")

    def test_pawn_cannot_retreat_and_cannot_cross_side_before_river(self):
        with self.assertRaises(ValueError):
            apply_move(START, "a3b3", "w")
        with self.assertRaises(ValueError):
            apply_move(START, "a3a2", "w")
        board = self.empty()
        board[4][0] = "P"
        self.assertEqual(apply_move(board, "a5b5", "w")[4][1], "P")


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.app = Controller(diagnostics=False)
        self.search = patch.object(self.app, "start_analysis")
        self.search.start()
        self.grade = patch("controller.grade_move", return_value={"status":"done", "played_score":30,
                          "score_unit":"cp", "loss":20, "label":"偏离首选", "played_evaluation":"红分 +30"})
        self.grade.start()
        self.app.board = deepcopy(REFERENCE)
        self.app.stable_board = deepcopy(REFERENCE)
        self.app.history = [{"move":None, "text":"模拟起点", "board":deepcopy(REFERENCE), "score":None}]

    def tearDown(self):
        self.app.close()
        self.search.stop()
        self.grade.stop()

    def test_point_move_grading_undo_and_live_resume(self):
        self.app.action("automatic", {"enabled":False})
        self.assertTrue(self.app.simulation_enabled)
        self.app.action("move", {"move":"c2e3", "generation":self.app.generation})
        self.assertEqual(self.app.board[6][4], "N")
        self.assertEqual(self.app.turn, "b")
        self.assertFalse(self.app.automatic)
        self.assertIn("a9a8", self.app.snapshot()["legal_moves"])
        deadline = time.monotonic()+2
        while time.monotonic() < deadline and self.app.snapshot()["move_rating"]["status"] == "pending":
            time.sleep(0.01)
        self.assertEqual(self.app.snapshot()["move_rating"]["played_score"], 30)
        self.app.action("move", {"move":"a9a8"})
        self.app.action("undo", {})
        self.assertEqual(self.app.turn, "b")
        self.assertEqual(len(self.app.simulation_stack), 1)
        self.app.action("simulation_reset", {})
        self.assertEqual(self.app.board, REFERENCE)
        self.assertEqual(self.app.simulation_stack, [])
        self.app.action("automatic", {"enabled":True})
        self.assertTrue(self.app.automatic)
        self.assertFalse(self.app.simulation_enabled)
        self.assertIsNone(self.app.board)

    def test_disappearing_game_does_not_delete_paused_practice(self):
        self.app.selected_hwnd = 123
        self.app.action("simulation", {})
        self.app.action("move", {"move":"c2e3"})
        expected = deepcopy(self.app.board)
        with patch("controller.list_game_windows", return_value=[]):
            self.app.refresh_windows()
        self.assertEqual(self.app.board, expected)
        self.assertTrue(self.app.simulation_enabled)

    def test_illegal_move_and_stale_client_do_not_mutate_board(self):
        self.app.action("simulation", {})
        with self.assertRaises(ValueError):
            self.app.action("move", {"move":"c2c3"})
        self.assertEqual(self.app.board, REFERENCE)
        with self.assertRaises(ValueError):
            self.app.action("move", {"move":"c2e3", "generation":self.app.generation-1})
        self.assertEqual(self.app.simulation_stack, [])

    def test_update_restores_paused_position_and_consumes_temporary_file(self):
        self.app.automatic = False
        state = self.app.snapshot()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "resume.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            self.app.reset_position()
            restore_snapshot(self.app, path)
            self.assertEqual(self.app.board, REFERENCE)
            self.assertEqual(self.app.history, state["history"])
            self.assertFalse(self.app.automatic)
            self.assertIsNone(self.app.turn)
            self.assertFalse(path.exists())


class EngineGradingTests(unittest.TestCase):
    def test_large_black_scores_and_loss_keep_native_units(self):
        def search(fen, seconds, callback, cancel, history, multipv, searchmoves=None):
            score, move = (1750, "c2e3") if searchmoves else (2300, "g2e3")
            callback(f"info depth 20 score cp {score} pv {move}")
            return move
        with patch("grading.analyze", side_effect=search):
            result = grade_move("unused", [], "c2e3", "b", 1, threading.Event())
        self.assertEqual(result["played_score"], -1750)
        self.assertEqual(result["best_score"], -2300)
        self.assertEqual(result["loss"], 550)
        self.assertEqual(result["played_evaluation"], "红分 -1750 · 黑方占优")
        self.assertNotIn("points", result)

    def test_mate_has_a_distance_instead_of_an_arbitrary_numeric_grade(self):
        def search(fen, seconds, callback, cancel, history, multipv, searchmoves=None):
            distance, move = (9, "c2e3") if searchmoves else (5, "g2e3")
            callback(f"info depth 20 score mate {distance} pv {move}")
            return move
        with patch("grading.analyze", side_effect=search):
            result = grade_move("unused", [], "c2e3", "b", 1, threading.Event())
        self.assertIsNone(result["played_score"])
        self.assertEqual(result["played_mate"], -9)
        self.assertIsNone(result["loss"])
        self.assertNotIn("points", result)

    @unittest.skipUnless(EXE.is_file() and NET.is_file(), "需要用户自行安装的 Pikafish 引擎和 NNUE")
    def test_real_engine_forced_root_move_and_step_rating(self):
        fen = to_fen(REFERENCE, "w")
        self.assertEqual(analyze(fen, 0.2, searchmoves=["c2e3"]), "c2e3")
        result = grade_move(fen, [], "c2e3", "w", 0.3, threading.Event())
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["move"], "c2e3")
        self.assertIn("红分", result["played_evaluation"])
        self.assertIsInstance(result["played_score"], int)
        self.assertNotIn("points", result)
        self.assertGreaterEqual(result["loss"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
