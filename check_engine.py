"""Verify the locally installed engine through its UCI interface."""
from pathlib import Path
import json
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "engine" / "Pikafish-Windows-x86-64-universal.exe"
NET = ROOT / "engine" / "pikafish.nnue"


def main():
    transcript = []
    lines = queue.Queue()
    process = subprocess.Popen(
        [str(EXE)], cwd=ROOT.parent, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    def reader():
        for line in process.stdout:
            lines.put(line.rstrip())
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()

    def send(command):
        transcript.append("> " + command)
        process.stdin.write(command + "\n")
        process.stdin.flush()

    def until(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
            if line is None:
                raise RuntimeError("Engine exited unexpectedly")
            transcript.append(line)
            if "CRITICAL ERROR" in line or line.startswith("info string ERROR:"):
                raise RuntimeError(line)
            if predicate(line):
                return line
        raise TimeoutError("Engine response timed out")

    try:
        send("uci")
        until(lambda line: line == "uciok")
        send("setoption name Threads value 4")
        send("setoption name Hash value 256")
        send("setoption name EvalFile value " + str(NET))
        send("isready")
        until(lambda line: line == "readyok")
        send("ucinewgame")
        send("position startpos")
        send("go movetime 1000")
        bestmove = until(lambda line: line.startswith("bestmove "))
        move = bestmove.split()[1]
        assert len(move) == 4 and move != "0000", bestmove
        send("position startpos moves " + move)
        send("go movetime 300")
        reply = until(lambda line: line.startswith("bestmove "))
        assert reply.split()[1] != "0000", reply
        send("position startpos")
        send("go perft 2")
        perft = until(lambda line: "Nodes searched:" in line)
        assert int(perft.split(":")[-1].strip()) == 1920, perft
        send("quit")
        assert process.wait(timeout=10) == 0
        result = {"passed": True, "bestmove": bestmove, "reply": reply,
                  "perft_depth_2": 1920, "threads": 4, "hash_mb": 256,
                  "exe": str(EXE), "eval_file": str(NET)}
        (ROOT / "verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        (ROOT / "uci-test.log").write_text("\n".join(transcript) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
