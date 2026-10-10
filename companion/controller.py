"""Local board monitor and versioned engine analysis, shared by the web UI."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import base64
import io
import json
import threading
import time
import queue
import subprocess
import sys
from PIL import Image
from capture import list_game_windows, capture_game, board_visible, capture_rect, region_from_grid
from engine import analyze, detect_move, parse_info
from vision import Recognizer, Geometry, locate_board, refine_grid, to_fen, describe_move
from variation import replay, evaluation
from rules import apply_move, legal_moves
from grading import grade_move

HERE = Path(__file__).resolve().parent


class Controller:
    def __init__(self, diagnostics=True):
        self.lock = threading.RLock()
        template_path = HERE / "templates.npz"
        self.recognizer = Recognizer.load(template_path) if template_path.exists() else Recognizer()
        self.window_recognizer = self.recognizer
        screen_path = HERE / "screen-templates.npz"
        self.screen_recognizer = Recognizer.load(screen_path) if screen_path.exists() else self.recognizer
        # A live-video skin can appear inside a window or a screen selection.
        # Retain the original samples while sharing available skin examples.
        if screen_path.exists() and self.recognizer.masks is not None:
            import numpy as np
            shared = Recognizer(np.concatenate((self.recognizer.masks, self.screen_recognizer.masks))[-500:],
                                np.concatenate((self.recognizer.labels, self.screen_recognizer.labels))[-500:])
            self.window_recognizer = self.screen_recognizer = self.recognizer = shared
        self.capture_mode = "window"
        self.screen_region = self.region_geometry = self.region_image = None
        self.picking_region = False
        self.picker_process = None
        self.diagnostics = diagnostics
        self.automatic = True
        self.turn_mode, self.turn = "auto", None
        self.board = self.stable_board = self.geometry = None
        self.preview = None
        self.uncertain, self.windows, self.history, self.moves = [], [], [], []
        self.selected_hwnd = self.base_fen = None
        self.pending_board, self.pending_count = None, 0
        self.variations, self.bestmoves = {}, {}
        self.seconds, self.multipv = 3.0, 3
        self.generation, self.analysis_running = 0, False
        self.status = "正在寻找天天象棋网页，请保持完整棋盘可见。"
        self.source, self.turn_reason = "网页", "等待识别"
        self.preview = None
        self.cancel = threading.Event()
        self.closed = threading.Event()
        self.monitor = self.search_thread = None
        self.last_client = time.monotonic()
        self.capture_epoch = 0
        self.simulation_enabled = False
        self.simulation_origin = None
        self.simulation_stack = []
        self.ratings = {}
        self.rating_sequence = 0
        self.grade_epoch = 0
        self.grade_queue = queue.Queue()
        self.grade_cancel = threading.Event()
        self.grade_thread = None
        self.active_rating = None
        self.legal_cache_key, self.legal_cache = None, []

    def start(self):
        self.monitor = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor.start()

    def invalidate(self):
        self.cancel.set()
        self.generation += 1
        self.variations, self.bestmoves = {}, {}
        self.analysis_running = False

    def reset_position(self):
        self.clear_simulation()
        self.capture_epoch += 1
        self.invalidate()
        self.board = self.stable_board = self.geometry = None
        self.preview = None
        self.pending_board, self.pending_count = None, 0
        self.region_image = None
        self.history, self.moves, self.uncertain = [], [], []
        self.base_fen = None
        self.turn = self.turn_mode if self.turn_mode != "auto" else None

    def refresh_windows(self):
        found = list_game_windows()
        with self.lock:
            self.windows = found
            if self.capture_mode == "window" and self.selected_hwnd not in [hwnd for hwnd, _ in found]:
                if self.selected_hwnd is not None and self.automatic:
                    self.reset_position()
                self.selected_hwnd = found[0][0] if len(found) == 1 else None

    def monitor_loop(self):
        while not self.closed.is_set():
            epoch = self.capture_epoch
            try:
                self.refresh_windows()
                with self.lock:
                    automatic, hwnd, epoch = self.automatic, self.selected_hwnd, self.capture_epoch
                    mode, region, geo = self.capture_mode, self.screen_region, deepcopy(self.region_geometry)
                if automatic:
                    if mode == "region":
                        if region is None:
                            raise ValueError("请先点击“框选屏幕棋盘”。")
                        image = capture_rect(region)
                        self.accept_image(image, geo, epoch=epoch)
                    elif hwnd is None:
                        with self.lock:
                            self.status = "请选择天天象棋窗口。" if self.windows else "等待天天象棋网页；请切换到显示棋盘的标签页。"
                    else:
                        image = capture_game(hwnd)
                        geo = locate_board(image)
                        if not board_visible(hwnd, geo):
                            raise ValueError("网页棋盘被遮挡，请与助手并排放置。")
                        self.accept_image(image, geo, hwnd=hwnd, epoch=epoch)
            except Exception as error:
                with self.lock:
                    if self.automatic and epoch == self.capture_epoch:
                        self.invalidate()
                        self.status = str(error)
                        self.pending_board, self.pending_count = None, 0
            self.closed.wait(0.9)

    def accept_image(self, image, geometry=None, stable=False, hwnd=None, epoch=None):
        with self.lock:
            if epoch is not None and (not self.automatic or epoch != self.capture_epoch):
                return
            recognizer = self.recognizer
        geo = refine_grid(image, geometry or locate_board(image))
        board, uncertain, _ = recognizer.recognize(image, geo)
        kings = {piece: [(r, c) for r in range(10) for c in range(9) if board[r][c] == piece] for piece in ("K", "k")}
        if (len(kings["K"]) == len(kings["k"]) == 1 and kings["K"][0][0] <= 2
                and kings["k"][0][0] >= 7 and not any(cell in uncertain for cells in kings.values() for cell in cells)):
            geo.red_bottom = not geo.red_bottom
            board, uncertain, _ = recognizer.recognize(image, geo)
        margin = min(geo.dx, geo.dy)*0.55
        crop = image.crop((max(0, int(geo.left-margin)), max(0, int(geo.top-margin)),
                           min(image.width, int(geo.right+margin)), min(image.height, int(geo.bottom+margin))))
        crop.thumbnail((700, 800))
        buffer = io.BytesIO()
        crop.save(buffer, format="JPEG", quality=88)
        with self.lock:
            if epoch is not None and (not self.automatic or epoch != self.capture_epoch):
                return
            if hwnd is not None and (hwnd != self.selected_hwnd or not self.automatic or epoch != self.capture_epoch):
                return
            if epoch is not None and self.capture_mode == "region":
                self.region_geometry = deepcopy(geo)
                self.region_image = image.copy()
            self.geometry, self.preview = geo, buffer.getvalue()
            self.board, self.uncertain = board, uncertain
            if uncertain:
                self.invalidate()
                self.pending_board, self.pending_count = None, 0
                self.status = f"{len(uncertain)} 处识别不确定：请移开鼠标和选中效果，或点击校正。"
                return
            to_fen(board, "w")
            if board != self.stable_board:
                self.invalidate()
            if board == self.pending_board:
                self.pending_count += 1
            else:
                self.pending_board, self.pending_count = deepcopy(board), 1
            if not stable and self.pending_count < 2:
                self.status = "等待落子动画结束…"
                return
            changed = board != self.stable_board
            old_board = self.stable_board
            if changed:
                detected = detect_move(old_board, board) if old_board is not None else None
                if detected:
                    move, next_turn = detected
                    mover = "w" if next_turn == "b" else "b"
                    if self.base_fen is None or self.turn != mover:
                        self.base_fen, self.moves = to_fen(old_board, mover), []
                    self.moves.append(move)
                    if self.turn_mode == "auto":
                        self.turn = next_turn
                        self.turn_reason = "根据上一手落子自动判断"
                    else:
                        self.turn = self.turn_mode
                        self.base_fen, self.moves = to_fen(board, self.turn), []
                        self.turn_reason = "手动指定分析方"
                    self.history.append({"move": move, "text": describe_move(old_board, move), "board": deepcopy(board), "score": None})
                else:
                    self.history = [{"move": None, "text": "开始监测的局面", "board": deepcopy(board), "score": None}]
                    self.moves, self.base_fen = [], None
                    self.turn = self.turn_mode if self.turn_mode != "auto" else None
                    self.turn_reason = "等待下一手落子；先分别分析红黑" if self.turn is None else "手动指定分析方"
                self.stable_board = deepcopy(board)
            self.status = "局面已识别，正在分析。" if self.analysis_running else "棋盘已识别。"
            if (changed or not self.variations) and not self.analysis_running:
                self.start_analysis()

    def start_analysis(self):
        with self.lock:
            if self.board is None or self.uncertain or self.board != self.stable_board:
                self.status = "等待完整、稳定的棋盘；识别不确定时暂停分析。"
                return
            self.invalidate()
            generation = self.generation
            self.cancel = cancel = threading.Event()
            self.analysis_running = True
            board = deepcopy(self.board)
            sides = [self.turn] if self.turn else ["w", "b"]
            seconds, multipv = self.seconds, self.multipv
            base_fen, history = self.base_fen, list(self.moves)
            known_turn = self.turn
            self.status = "皮卡鱼正在搜索后续变化…"

        def callback(side, line):
            info = parse_info(line)
            if info is None:
                return
            try:
                _, descriptions = replay(board, info["moves"], side)
            except ValueError:
                return
            info.update({"side": side, "evaluation": evaluation(info, side), "notations": descriptions})
            with self.lock:
                if generation != self.generation or cancel.is_set():
                    return
                key = f"{side}{info['rank']}"
                previous = self.variations.get(key)
                if previous and not previous.get("bound") and info.get("bound"):
                    return
                if previous and previous["depth"] > info["depth"]:
                    return
                self.variations[key] = info

        def worker():
            try:
                for side in sides:
                    if cancel.is_set():
                        raise InterruptedError()
                    fen = base_fen if known_turn and base_fen else to_fen(board, side)
                    moves = history if known_turn and base_fen else []
                    best = analyze(fen, seconds, lambda line, side=side: callback(side, line), cancel, moves, multipv)
                    with self.lock:
                        if generation != self.generation or cancel.is_set():
                            return
                        self.bestmoves[side] = best
                with self.lock:
                    if generation == self.generation and not cancel.is_set():
                        self.analysis_running = False
                        self.status = "分析完成，自动跟随局面。" if self.automatic else "分析完成。"
                        primary = self.variations.get(f"{self.turn}1") if self.turn else None
                        if primary and primary["unit"] == "cp" and self.history:
                            self.history[-1]["score"] = primary["score"] * (1 if self.turn == "w" else -1)
                        self.write_diagnostics()
            except InterruptedError:
                pass
            except Exception as error:
                with self.lock:
                    if generation == self.generation:
                        self.analysis_running = False
                        self.status = "引擎分析失败：" + str(error)
        self.search_thread = threading.Thread(target=worker, daemon=False)
        self.search_thread.start()

    def snapshot(self):
        with self.lock:
            self.last_client = time.monotonic()
            try:
                fen = to_fen(self.board, self.turn or "w") if self.board and not self.uncertain else None
            except ValueError:
                fen = None
            playable = self.simulation_enabled and not self.automatic and fen and self.board == self.stable_board
            cache_key = (fen, self.turn) if playable else None
            if cache_key != self.legal_cache_key:
                self.legal_cache_key = cache_key
                self.legal_cache = legal_moves(self.board, self.turn) if playable else []
            history = deepcopy(self.history)
            for item in history:
                item["rating"] = self.ratings.get(item.get("rating_id"))
            data = {"generation": self.generation, "automatic": self.automatic, "turn": self.turn,
                    "turn_mode": self.turn_mode, "turn_reason": self.turn_reason, "board": self.board,
                    "uncertain": self.uncertain, "geometry": asdict(self.geometry) if self.geometry else None,
                    "status": self.status, "source": self.source, "seconds": self.seconds, "multipv": self.multipv,
                    "capture_mode": self.capture_mode, "screen_region": self.screen_region,
                    "region_geometry": asdict(self.region_geometry) if self.region_geometry else None,
                    "picking_region": self.picking_region,
                    "windows": [{"id": hwnd, "title": title} for hwnd, title in self.windows],
                    "selected_window": self.selected_hwnd, "variations": sorted(self.variations.values(), key=lambda v: (v["side"] != "w", v["rank"])),
                    "bestmoves": self.bestmoves, "analysis_running": self.analysis_running,
                    "history": history, "fen": fen, "simulation_enabled": self.simulation_enabled,
                    "simulation_plies": len(self.simulation_stack), "legal_moves": self.legal_cache if playable else [],
                    "move_rating": next((item.get("rating") for item in reversed(history) if item.get("rating")), None),
                    "score_unit": "cp"}
            return deepcopy(data)

    def action(self, name, data):
        with self.lock:
            if name == "automatic":
                self.capture_epoch += 1
                source = "屏幕区域" if self.capture_mode == "region" else "网页"
                if bool(data["enabled"]) and (self.source != source or self.simulation_enabled):
                    self.reset_position()
                self.automatic = bool(data["enabled"])
                if not self.automatic and self.board is not None and not self.uncertain and self.board == self.stable_board:
                    self.enable_simulation()
                self.source = source if self.automatic else self.source
                self.status = "实时同步已开启，正在读取所选来源。" if self.automatic else "实时同步已关闭，可以在棋盘上模拟走棋。"
            elif name == "pick_region":
                self.pick_region()
            elif name == "learn_region":
                self.learn_region()
            elif name == "region":
                if self.screen_region is None or self.region_geometry is None:
                    raise ValueError("请先框选屏幕棋盘。")
                self.set_screen_region({"rect": self.screen_region, "geometry": asdict(self.region_geometry)})
            elif name == "simulation":
                self.enable_simulation()
            elif name == "move":
                self.simulate_move(data["move"], data.get("generation"))
            elif name in ("undo", "simulation_reset"):
                self.restore_simulation(origin=name == "simulation_reset")
            elif name == "window":
                hwnd = int(data["id"])
                if hwnd not in [item[0] for item in self.windows]:
                    raise ValueError("窗口已关闭，请重新选择。")
                self.reset_position()
                self.capture_mode = "window"
                self.recognizer = self.window_recognizer
                self.selected_hwnd, self.automatic, self.source = hwnd, True, "网页"
            elif name == "analyze":
                self.start_analysis()
            elif name == "settings":
                self.seconds = min(30.0, max(0.2, float(data.get("seconds", self.seconds))))
                self.multipv = min(5, max(1, int(data.get("multipv", self.multipv))))
                self.start_analysis()
            elif name == "side":
                mode = data["side"]
                if mode not in ("auto", "w", "b"):
                    raise ValueError("行棋方不合法")
                self.turn_mode = mode
                self.turn = mode if mode != "auto" else None
                self.base_fen, self.moves = None, []
                self.turn_reason = "手动指定分析方" if self.turn else "等待落子判断，分别分析红黑"
                self.start_analysis()
            elif name == "correct":
                r, c, piece = int(data["row"]), int(data["col"]), data["piece"]
                if self.board is None or not (0 <= r < 10 and 0 <= c < 9) or piece not in ".rnbakcpRNBAKCP":
                    raise ValueError("校正位置或棋子不合法")
                self.automatic = False
                self.capture_epoch += 1
                self.clear_simulation()
                self.invalidate()
                self.board[r][c] = piece
                self.uncertain = [cell for cell in self.uncertain if cell != (r, c)]
                if not self.uncertain:
                    try:
                        to_fen(self.board, "w")
                        self.stable_board = deepcopy(self.board)
                    except ValueError:
                        self.stable_board = None
                    self.base_fen, self.moves = None, []
                self.status = "位置已校正；可重新分析，再开启自动识别。"
            elif name == "reset":
                self.reset_position()
                self.status = "已清空记录，等待新局面。"
            else:
                raise ValueError("未知操作")

    def import_image(self, encoded):
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 8_000_000:
            raise ValueError("截图过大，请裁剪到棋盘。")
        image = Image.open(io.BytesIO(raw))
        if image.width*image.height > 24_000_000:
            raise ValueError("截图像素过多，请裁剪到棋盘。")
        image = image.convert("RGB")
        with self.lock:
            self.automatic, self.source = False, "导入截图"
            self.reset_position()
        self.accept_image(image, stable=True)

    def set_screen_region(self, selection):
        """Called only with the native picker's validated physical grid points."""
        rect, values = selection["rect"], selection["geometry"]
        points = [round(rect[0]+values["left"]), round(rect[1]+values["top"]),
                  round(rect[0]+values["right"]), round(rect[1]+values["bottom"])]
        selected = region_from_grid(points)
        geometry = Geometry(**selected["geometry"])
        geometry.validate((selected["rect"][2]-selected["rect"][0], selected["rect"][3]-selected["rect"][1]))
        with self.lock:
            self.reset_position()
            self.capture_mode, self.source = "region", "屏幕区域"
            self.screen_region, self.region_geometry = selected["rect"], geometry
            self.recognizer = self.screen_recognizer
            self.automatic = True
            self.status = "已框选屏幕棋盘，等待直播画面稳定。"

    def pick_region(self):
        if self.picking_region:
            raise ValueError("正在框选；请按 Enter 确认或 Esc 取消。")
        self.picking_region = True
        previous_automatic = self.automatic
        self.automatic = False
        self.capture_epoch += 1
        epoch = self.capture_epoch
        self.invalidate()
        self.status = "在桌面拖动框选棋盘交叉点；Enter 确认，Esc 取消。"

        def worker():
            process = None
            try:
                with self.lock:
                    if self.closed.is_set():
                        return
                    process = self.picker_process = subprocess.Popen(
                        [sys.executable, str(HERE / "region_picker.py")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                        creationflags=subprocess.CREATE_NO_WINDOW)
                output, unused = process.communicate(timeout=190)
                result = json.loads(output)
                with self.lock:
                    if epoch != self.capture_epoch or self.closed.is_set():
                        return
                    if result.get("error"):
                        raise ValueError(result["error"])
                    if result.get("selection"):
                        self.set_screen_region(result["selection"])
                    else:
                        self.automatic = previous_automatic
                        self.status = "已取消框选，保留原来的识别来源。"
            except Exception as error:
                if process and process.poll() is None:
                    process.kill()
                    process.communicate()
                with self.lock:
                    if epoch == self.capture_epoch and not self.closed.is_set():
                        self.automatic = previous_automatic
                        self.status = "框选失败：" + str(error)
            finally:
                with self.lock:
                    self.picking_region = False
                    self.picker_process = None
        threading.Thread(target=worker, daemon=True).start()

    def learn_region(self):
        if self.capture_mode != "region" or self.region_image is None or self.geometry is None:
            raise ValueError("请先框选屏幕棋盘并读取一次画面。")
        if self.automatic or self.simulation_stack or self.uncertain or self.board != self.stable_board:
            raise ValueError("请关闭同步、核对并校正全部棋子，退出模拟后再学习当前皮肤。")
        to_fen(self.board, self.turn or "w")
        fresh = Recognizer()
        fresh.calibrate(self.region_image, self.geometry, self.board)
        observed, uncertain, unused = fresh.recognize(self.region_image, self.geometry)
        if observed != self.board or uncertain:
            raise ValueError("这张画面不能稳定区分棋子；请放大直播棋盘后重试。")
        # Retain absent piece classes from previous templates, capped at 500.
        import numpy as np
        old = self.screen_recognizer
        if old.masks is not None:
            fresh.masks = np.concatenate((old.masks[-410:], fresh.masks))
            fresh.labels = np.concatenate((old.labels[-410:], fresh.labels))
        fresh.save(HERE / "screen-templates.npz")
        self.clear_simulation()
        self.screen_recognizer = self.recognizer = fresh
        self.window_recognizer = fresh
        self.status = "已在本机学习屏幕棋盘皮肤；可开启实时同步。"

    def write_diagnostics(self):
        if self.diagnostics:
            try:
                data = {"status": self.status, "turn": self.turn, "turn_reason": self.turn_reason,
                        "automatic": self.automatic, "bestmoves": self.bestmoves,
                        "variations": self.variations, "geometry": asdict(self.geometry) if self.geometry else None}
                data.update(simulation_enabled=self.simulation_enabled, simulation_plies=len(self.simulation_stack))
                (HERE / "web-status.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass

    def close(self):
        self.closed.set()
        self.cancel.set()
        self.grade_cancel.set()
        with self.lock:
            if self.picker_process and self.picker_process.poll() is None:
                self.picker_process.terminate()
        for thread in (self.monitor, self.search_thread, self.grade_thread):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=3)

    def checkpoint(self):
        return deepcopy({name: getattr(self, name) for name in
                         ("board", "stable_board", "history", "moves", "base_fen", "turn", "turn_mode", "turn_reason", "source")})

    def clear_simulation(self):
        self.grade_epoch += 1
        self.grade_cancel.set()
        self.simulation_enabled = False
        self.simulation_origin = None
        self.simulation_stack = []
        self.ratings = {}
        self.legal_cache_key, self.legal_cache = None, []

    def enable_simulation(self):
        if self.board is None or self.uncertain or self.board != self.stable_board:
            raise ValueError("请先读取一个完整、稳定的局面。")
        if self.simulation_origin is None:
            self.simulation_origin = self.checkpoint()
        self.capture_epoch += 1
        self.automatic = False
        self.simulation_enabled = True
        self.status = "已关闭实时同步；点棋子，再点绿色落点模拟。"

    def simulate_move(self, move, generation=None):
        if generation is not None and int(generation) != self.generation:
            raise ValueError("局面已经改变，请重新选择棋子。")
        if not self.simulation_enabled or self.automatic:
            raise ValueError("请先进入模拟走棋，或关闭实时同步。")
        if self.board is None or self.uncertain or self.board != self.stable_board:
            raise ValueError("请先核对和校正棋盘。")
        from rules import squares
        r1, c1, _, _ = squares(move)
        piece = self.board[r1][c1]
        mover = self.turn or ("w" if piece.isupper() else "b")
        position = apply_move(self.board, move, mover)
        checkpoint = self.checkpoint()
        text = describe_move(self.board, move)
        fen = self.base_fen if self.base_fen and self.turn == mover else to_fen(self.board, mover)
        prior_moves = list(self.moves) if self.base_fen and self.turn == mover else []
        self.simulation_stack.append(checkpoint)
        self.board = self.stable_board = position
        self.pending_board, self.pending_count = deepcopy(position), 2
        self.base_fen, self.moves = fen, prior_moves+[move]
        self.turn_mode, self.turn = "auto", ("b" if mover == "w" else "w")
        self.turn_reason = "模拟落子后自动轮换行棋方"
        self.source = "模拟推演"
        self.rating_sequence += 1
        rating_id = str(self.rating_sequence)
        self.ratings[rating_id] = {"status": "pending", "text": text, "label": "等待评分"}
        if not self.history:
            self.history = [{"move": None, "text": "模拟起点", "board": deepcopy(checkpoint["board"]), "score": None}]
        self.history.append({"move": move, "text": text, "board": deepcopy(position), "score": None,
                             "simulation": True, "rating_id": rating_id})
        self.start_analysis()
        budget = min(10.0, self.seconds)
        self.grade_queue.put({"id": rating_id, "epoch": self.grade_epoch, "fen": fen,
                              "history": prior_moves, "move": move, "turn": mover, "seconds": budget, "text": text,
                              "board": checkpoint["board"]})
        if self.grade_thread is None or not self.grade_thread.is_alive():
            self.grade_thread = threading.Thread(target=self.grade_loop, daemon=False)
            self.grade_thread.start()

    def restore_simulation(self, origin=False):
        if not self.simulation_enabled:
            raise ValueError("当前未处于模拟模式。")
        if origin:
            if self.simulation_origin is None:
                return
            checkpoint = deepcopy(self.simulation_origin)
            self.simulation_stack = []
        elif self.simulation_stack:
            checkpoint = self.simulation_stack.pop()
        else:
            raise ValueError("已经在模拟起点。")
        self.invalidate()
        for name, value in checkpoint.items():
            setattr(self, name, deepcopy(value))
        self.automatic = False
        self.pending_board, self.pending_count = deepcopy(self.board), 2
        retained = {item.get("rating_id") for item in self.history}
        if self.active_rating not in retained:
            self.grade_cancel.set()
        self.start_analysis()

    def grade_loop(self):
        while not self.closed.is_set():
            try:
                job = self.grade_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            with self.lock:
                retained = {item.get("rating_id") for item in self.history}
                if job["epoch"] != self.grade_epoch or job["id"] not in retained:
                    continue
                self.grade_cancel = cancel = threading.Event()
                self.active_rating = job["id"]
                self.ratings[job["id"]]["label"] = "皮卡鱼评分中…"
            try:
                result = grade_move(job["fen"], job["history"], job["move"], job["turn"], job["seconds"], cancel)
                result["text"] = job["text"]
                if result.get("bestmove"):
                    result["best_text"] = describe_move(job["board"], result["bestmove"]).split("（", 1)[0]
            except InterruptedError:
                result = {"status": "cancelled", "text": job["text"], "label": "评分已中止"}
            except Exception as error:
                result = {"status": "error", "text": job["text"], "label": "评分失败："+str(error)}
            with self.lock:
                if job["epoch"] == self.grade_epoch and job["id"] in {item.get("rating_id") for item in self.history}:
                    self.ratings[job["id"]] = result
                if self.active_rating == job["id"]:
                    self.active_rating = None
