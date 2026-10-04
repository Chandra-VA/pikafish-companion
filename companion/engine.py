"""A bounded UCI analysis session; no network, no game input."""
from pathlib import Path
import queue
import subprocess
import threading
import time
import re

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "engine" / "Pikafish-Windows-x86-64-universal.exe"
NET = ROOT / "engine" / "pikafish.nnue"


def analyze(fen, seconds=1.0, callback=None, cancel=None, moves=None, multipv=1, searchmoves=None):
    seconds = min(30.0, max(0.2, float(seconds)))
    multipv = min(5, max(1, int(multipv)))
    lines = queue.Queue()
    process = subprocess.Popen([str(EXE)], cwd=EXE.parent, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", bufsize=1,
                               creationflags=subprocess.CREATE_NO_WINDOW)

    def read():
        for line in process.stdout:
            lines.put(line.rstrip())
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()

    def send(command):
        process.stdin.write(command + "\n")
        process.stdin.flush()

    def wait(predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel and cancel.is_set():
                raise InterruptedError("分析已取消")
            try:
                line = lines.get(timeout=min(0.1, max(0.01, deadline-time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError("引擎退出，请检查棋盘识别、行棋方和 NNUE 文件。")
            if "CRITICAL ERROR" in line or line.startswith("info string ERROR:"):
                raise RuntimeError(line)
            if callback and line.startswith("info depth "):
                callback(line)
            if predicate(line):
                return line
        raise TimeoutError("引擎响应超时")

    try:
        send("uci")
        wait(lambda line: line == "uciok", 20)
        send("setoption name Threads value 2")
        send("setoption name Hash value 128")
        send("setoption name Ponder value false")
        send("setoption name MultiPV value " + str(multipv))
        send("setoption name EvalFile value " + str(NET))
        send("isready")
        wait(lambda line: line == "readyok", 20)
        if ("\n" in fen or "\r" in fen or (moves and any(not valid_move(move) for move in moves))
                or (searchmoves is not None and (not searchmoves or any(not valid_move(move) for move in searchmoves)))):
            raise ValueError("局面或着法格式不合法")
        send("position fen " + fen + (" moves " + " ".join(moves) if moves else ""))
        send("go movetime " + str(int(seconds*1000)) + (" searchmoves " + " ".join(searchmoves) if searchmoves else ""))
        result = wait(lambda line: line.startswith("bestmove "), seconds+20)
        send("quit")
        process.wait(timeout=5)
        if process.returncode != 0:
            raise RuntimeError("引擎异常退出")
        return result.split()[1]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


def valid_move(move):
    return (len(move) == 4 and move[0] in "abcdefghi" and move[2] in "abcdefghi"
            and move[1] in "0123456789" and move[3] in "0123456789")


def parse_info(line):
    """Parse only scored search lines with an actual principal variation."""
    score = re.search(r"\bscore (cp|mate) (-?\d+)(?: (lowerbound|upperbound))?", line)
    depth = re.search(r"\bdepth (\d+)", line)
    if not score or not depth or " pv " not in line:
        return None
    moves = line.split(" pv ", 1)[1].split()
    if not moves or any(not valid_move(move) for move in moves):
        return None
    rank = re.search(r"\bmultipv (\d+)", line)
    return {"depth": int(depth[1]), "rank": int(rank[1]) if rank else 1,
            "unit": score[1], "score": int(score[2]), "bound": score[3], "moves": moves}


def detect_move(previous, current):
    changes = [(r, c) for r in range(10) for c in range(9) if previous[r][c] != current[r][c]]
    if len(changes) != 2:
        return None
    sources = [(r, c) for r, c in changes if previous[r][c] != "." and current[r][c] == "."]
    if len(sources) != 1:
        return None
    r1, c1 = sources[0]
    r2, c2 = next(cell for cell in changes if cell != sources[0])
    piece, destination = previous[r1][c1], previous[r2][c2]
    if current[r2][c2] != piece or (destination != "." and destination.isupper() == piece.isupper()):
        return None
    return f"{chr(97+c1)}{9-r1}{chr(97+c2)}{9-r2}", ("b" if piece.isupper() else "w")
