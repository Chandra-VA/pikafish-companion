"""Loopback-only UI server, with same-origin and per-run token checks."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from copy import deepcopy
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from capture import setup_dpi
from controller import Controller
from vision import Geometry, to_fen

HERE = Path(__file__).resolve().parent
PORT = 18765


def make_server(controller, port=PORT):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def respond(self, content, kind="application/json; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def allowed(self, authenticate=False):
            address = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != address or self.headers.get("Origin") not in (None, f"http://{address}"):
                self.respond(b'{"error":"origin rejected"}', code=403)
                return False
            if authenticate and not secrets.compare_digest(self.headers.get("X-Pika-Token", ""), token):
                self.respond(b'{"error":"token required"}', code=403)
                return False
            return True

        def do_GET(self):
            self.path = urlsplit(self.path).path
            if not self.allowed(self.path.startswith("/api/")):
                return
            try:
                if self.path in ("/", "/index.html"):
                    html = (HERE / "web" / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                    self.respond(html.encode(), "text/html; charset=utf-8")
                elif self.path == "/health":
                    self.respond(b'{"app":"pika-companion-v2"}')
                elif self.path == "/api/state":
                    self.respond(json.dumps(controller.snapshot(), ensure_ascii=False).encode())
                elif self.path == "/api/preview":
                    with controller.lock:
                        preview = controller.preview
                    self.respond(preview or b"", "image/jpeg", 200 if preview else 404)
                elif self.path in ("/styles.css", "/main.js"):
                    self.respond((HERE / "web" / self.path[1:]).read_bytes(), "text/css" if self.path.endswith(".css") else "text/javascript; charset=utf-8")
                else:
                    self.respond(b'{"error":"not found"}', code=404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.respond(json.dumps({"error": str(error)}, ensure_ascii=False).encode(), code=500)

        def do_POST(self):
            if not self.allowed(True):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 12_000_000:
                    raise ValueError("请求大小不合法")
                data = json.loads(self.rfile.read(length))
                name = self.path.removeprefix("/api/")
                if name == "image":
                    controller.import_image(data["image"])
                else:
                    controller.action(name, data)
                self.respond(b'{"ok":true}')
            except (ValueError, KeyError, TypeError) as error:
                self.respond(json.dumps({"error": str(error)}, ensure_ascii=False).encode(), code=400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.respond(json.dumps({"error": str(error)}, ensure_ascii=False).encode(), code=500)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def open_ui():
    url = f"http://127.0.0.1:{PORT}/?v=integer-scores-1"
    edge = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"
    if edge.exists():
        subprocess.Popen([str(edge), "--app=" + url, "--window-size=940,900", "--window-position=975,35"])
    else:
        import webbrowser
        webbrowser.open(url)


def restore_snapshot(controller, path):
    """Consume a locally saved paused position when restarting for an update."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    board, turn = data["board"], data.get("turn")
    to_fen(board, turn or "w")
    if data.get("uncertain") or data.get("automatic"):
        raise ValueError("只能恢复已暂停、完整的局面")
    controller.board = deepcopy(board)
    controller.stable_board = deepcopy(board)
    controller.history = deepcopy(data.get("history", []))
    controller.turn, controller.turn_mode = turn, data.get("turn_mode", "auto")
    controller.turn_reason = data.get("turn_reason", "已恢复暂停局面")
    controller.source = data.get("source", "网页")
    controller.automatic = False
    controller.seconds, controller.multipv = data.get("seconds", 3), data.get("multipv", 3)
    controller.selected_hwnd = data.get("selected_window")
    if data.get("geometry"):
        controller.geometry = Geometry(**data["geometry"])
    controller.start_analysis()
    Path(path).unlink()


def main(resume=None):
    setup_dpi()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as response:
            if json.load(response).get("app") == "pika-companion-v2":
                open_ui()
                return
    except Exception:
        pass
    controller = Controller()
    server = make_server(controller)
    if resume is None and (HERE / ".upgrade-session.json").exists():
        resume = HERE / ".upgrade-session.json"
    if resume:
        restore_snapshot(controller, resume)
    controller.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    open_ui()
    try:
        while thread.is_alive() and time.monotonic()-controller.last_client < 120:
            time.sleep(2)
    finally:
        controller.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="恢复更新前暂存的暂停局面")
    main(parser.parse_args().resume)
