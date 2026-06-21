#!/usr/bin/env python3
"""Local-only server for the ilmavalvontaseloste app.

Serves the static frontend (index.html/app.js/style.css) and a reports.json
file that the frontend polls. Also exposes a tiny internal endpoint the voice
pipeline (whisper -> parser.py) can POST parsed reports to, which get
appended to reports.json with a timestamp.

Binds to 127.0.0.1 only - never exposed to the network.
"""
import json
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BIND_HOST = "127.0.0.1"
BIND_PORT = 8642
APP_DIR = Path(__file__).parent
REPORTS_FILE = APP_DIR / "reports.json"
CONFIG_FILE = APP_DIR / "config.json"
LEVEL_FILE = APP_DIR / "level.json"
PIPELINE_SCRIPT = APP_DIR / "live_pipeline.py"
PIPELINE_LOG = Path("/tmp/live_pipeline.log")
HEARTBEAT_STALE_AFTER_SECONDS = 3
STATIC_DIR = APP_DIR

_lock = threading.Lock()
_pipeline_lock = threading.Lock()
_pipeline_proc = None


def _start_pipeline():
    global _pipeline_proc
    with _pipeline_lock:
        if _pipeline_proc and _pipeline_proc.poll() is None:
            return False  # already running
        log_fh = open(PIPELINE_LOG, "a")
        _pipeline_proc = subprocess.Popen(
            [sys.executable, str(PIPELINE_SCRIPT)],
            cwd=str(APP_DIR), stdout=log_fh, stderr=subprocess.STDOUT,
        )
        return True


def _stop_pipeline():
    global _pipeline_proc
    with _pipeline_lock:
        if not (_pipeline_proc and _pipeline_proc.poll() is None):
            return False  # not running
        _pipeline_proc.terminate()
        try:
            _pipeline_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _pipeline_proc.kill()
        return True


def _pipeline_status():
    running = _pipeline_proc is not None and _pipeline_proc.poll() is None
    heartbeat_age = None
    if LEVEL_FILE.exists():
        heartbeat_age = time.time() - LEVEL_FILE.stat().st_mtime
    listening = running and heartbeat_age is not None and heartbeat_age < HEARTBEAT_STALE_AFTER_SECONDS
    return {"running": running, "listening": listening, "heartbeatAgeSeconds": heartbeat_age}


def _load_reports():
    if not REPORTS_FILE.exists():
        return []
    try:
        return json.loads(REPORTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_reports(reports):
    REPORTS_FILE.write_text(json.dumps(reports, ensure_ascii=False), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/reports.json":
            with _lock:
                self._send_json(200, _load_reports())
            return
        if self.path == "/pipeline/status":
            self._send_json(200, _pipeline_status())
            return
        # fall back to serving static files
        return self._serve_static()

    def do_POST(self):
        if self.path == "/ingest":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            parsed["timestamp"] = parsed.get("timestamp") or int(time.time() * 1000)

            with _lock:
                reports = _load_reports()
                reports.append(parsed)
                _save_reports(reports)

            self._send_json(200, {"status": "ok", "timestamp": parsed["timestamp"]})
            return

        if self.path == "/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                partial_config = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            with _lock:
                try:
                    current_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    current_config = {}
                current_config.update(partial_config)
                CONFIG_FILE.write_text(json.dumps(current_config, ensure_ascii=False), encoding="utf-8")

            self._send_json(200, {"status": "ok", "config": current_config})
            return

        if self.path == "/pipeline/start":
            started = _start_pipeline()
            self._send_json(200, {"started": started, **_pipeline_status()})
            return

        if self.path == "/pipeline/stop":
            stopped = _stop_pipeline()
            self._send_json(200, {"stopped": stopped, **_pipeline_status()})
            return

        if self.path == "/reports/clear":
            with _lock:
                _save_reports([])
            self._send_json(200, {"status": "ok"})
            return

        self._send_json(404, {"error": "not found"})

    def _serve_static(self):
        rel_path = self.path.lstrip("/") or "index.html"
        file_path = (STATIC_DIR / rel_path).resolve()
        if STATIC_DIR.resolve() not in file_path.parents and file_path != STATIC_DIR.resolve():
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }
        content_type = content_types.get(file_path.suffix, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # quiet by default


if __name__ == "__main__":
    if not REPORTS_FILE.exists():
        _save_reports([])
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print(f"Serving on http://{BIND_HOST}:{BIND_PORT} (localhost only)")
    server.serve_forever()
