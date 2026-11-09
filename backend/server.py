"""
Python Middle-Layer Backend for OpenCV Live Screen Analytics Dashboard.
Serves live telemetry, Server-Sent Events (SSE) streaming, frame refresh,
and snapshot feeds to the React Vite frontend.
Optimized for 3 core fields: HP, Player Name, and Eliminations.
"""

import os
import sys
import json
import time
import glob
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure vision package can be imported
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
VISION_DIR = os.path.join(PROJECT_ROOT, "vision")
EVENTS_DIR = os.path.join(PROJECT_ROOT, "events")
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "recordings", "snapshots")
DIST_DIR = os.path.join(PROJECT_ROOT, "frontend", "opencv-live-dashboard", "dist")

TELEMETRY_JSON = os.path.join(EVENTS_DIR, "live_telemetry.json")
LATEST_FRAME_PATH = os.path.join(RECORDINGS_DIR, "latest_frame.jpg")
CONFIG_PATH = os.path.join(VISION_DIR, "roi_config.json")

if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

from telemetry_extractor import FreeFireSpectatorParser, export_telemetry_json

PORT = 8000
_parser = FreeFireSpectatorParser()
CURRENT_MODE = "auto"


def get_latest_telemetry() -> Dict[str, Any]:
    """Reads latest live_telemetry.json or returns default packet."""
    if os.path.isfile(TELEMETRY_JSON):
        try:
            with open(TELEMETRY_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass

    return {
        "timestamp": datetime.now().isoformat(),
        "source": "standby",
        "game": "Free Fire",
        "mode": CURRENT_MODE,
        "is_squad": False,
        "team_name": "SQUAD",
        "team_eliminations": 0,
        "squad_members": [],
        "hp_bar": {"level": 0, "max": 200, "percentage": 0.0, "status": "UNKNOWN"},
        "playername": {"active": False, "score": 0.0, "value": "STANDBY"},
        "eliminations": {"count": 0, "active": False, "score": 0.0},
        "hp_level": 0,
        "player_name_active": False,
        "eliminations_count": 0,
        "screen_stats": {}
    }


def get_latest_snapshot_path() -> Optional[str]:
    """Finds the most recent HUD snapshot image."""
    global CURRENT_MODE

    # Check snapshots directory for most recent valid full game screen image
    if os.path.isdir(RECORDINGS_DIR):
        files = [
            f for f in glob.glob(os.path.join(RECORDINGS_DIR, "*.jpg")) + glob.glob(os.path.join(RECORDINGS_DIR, "*.png"))
            if not os.path.basename(f).startswith("_")
            and os.path.basename(f) != "latest_frame.jpg"
            and os.path.getsize(f) > 5000
        ]
        if files:
            files.sort(key=os.path.getmtime, reverse=True)
            return files[0]

    # Fallback to latest_frame if nothing else
    if os.path.isfile(LATEST_FRAME_PATH) and os.path.getsize(LATEST_FRAME_PATH) > 500:
        return LATEST_FRAME_PATH

    return None


def trigger_frame_refresh() -> Dict[str, Any]:
    """
    Executes an immediate synchronous OCR and telemetry frame extraction.
    Pulls from the latest captured screen or active snapshot image.
    """
    global CURRENT_MODE
    import cv2

    rois = {}
    calib = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                rois = cfg.get("rois", {})
                calib = cfg.get("monitor", {})
        except Exception:
            pass

    snap_path = get_latest_snapshot_path()
    if not snap_path:
        snap_path = os.path.join(RECORDINGS_DIR, "uploaded_test_screen.jpg")

    if snap_path and os.path.isfile(snap_path):
        frame = cv2.imread(snap_path)
        if frame is not None:
            data = _parser.parse_frame(frame, rois, calib_resolution=calib, sync_ocr=True)
            export_telemetry_json(
                output_path=TELEMETRY_JSON,
                telemetry_data=data,
                source=os.path.basename(snap_path)
            )
            return data

    return get_latest_telemetry()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handles requests in separate threads for non-blocking streaming."""
    daemon_threads = True


class AnalyticsAPIHandler(BaseHTTPRequestHandler):
    """CORS-enabled REST and SSE API handler for React live dashboard."""

    def _set_cors_headers(self, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")

    def do_OPTIONS(self):
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/api/refresh", "/api/refresh_frame"]:
            data = trigger_frame_refresh()
            self._set_cors_headers("application/json")
            self.end_headers()
            resp = {
                "status": "refreshed",
                "timestamp": datetime.now().isoformat(),
                "telemetry": data
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        elif path == "/api/mode":
            global CURRENT_MODE
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                parsed_body = json.loads(body)
                new_mode = parsed_body.get("mode", "auto").lower()
                if new_mode in ["solo", "squad", "auto"]:
                    CURRENT_MODE = new_mode
            except Exception:
                pass
            data = trigger_frame_refresh()
            self._set_cors_headers("application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "mode": CURRENT_MODE, "telemetry": data}).encode("utf-8"))
        else:
            self.send_error(404, "Endpoint not found")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. GET /api/telemetry
        if path == "/api/telemetry":
            self._set_cors_headers("application/json")
            self.end_headers()
            data = get_latest_telemetry()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        # 2. GET /api/refresh
        elif path in ["/api/refresh", "/api/refresh_frame"]:
            data = trigger_frame_refresh()
            self._set_cors_headers("application/json")
            self.end_headers()
            resp = {
                "status": "refreshed",
                "timestamp": datetime.now().isoformat(),
                "telemetry": data
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        # 3. GET /api/stream (Server-Sent Events)
        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    data = get_latest_telemetry()
                    payload = {
                        "telemetry": data,
                        "server_time": time.time()
                    }
                    event_data = f"data: {json.dumps(payload)}\n\n"
                    self.wfile.write(event_data.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.15)  # ~7 Hz streaming update
            except (BrokenPipeError, ConnectionResetError):
                pass

        # 4. GET /api/snapshot (Latest screenshot)
        elif path == "/api/snapshot":
            snap_path = get_latest_snapshot_path()
            if snap_path and os.path.isfile(snap_path):
                self._set_cors_headers("image/jpeg")
                self.end_headers()
                try:
                    with open(snap_path, "rb") as img_f:
                        self.wfile.write(img_f.read())
                except Exception:
                    pass
            else:
                self.send_error(404, "No snapshot available")

        # 5. GET /api/status (Health / Server stats)
        elif path in ["/api/status", "/api/health"]:
            self._set_cors_headers("application/json")
            self.end_headers()
            status = {
                "status": "online",
                "service": "OpenCV Live Analytics Middle-Layer",
                "port": PORT,
                "mode": CURRENT_MODE,
                "telemetry_file": TELEMETRY_JSON,
                "telemetry_exists": os.path.isfile(TELEMETRY_JSON),
                "snapshots_available": get_latest_snapshot_path() is not None,
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(status).encode("utf-8"))

        # 6. GET /api/mode
        elif path == "/api/mode":
            self._set_cors_headers("application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"mode": CURRENT_MODE}).encode("utf-8"))

        # 6. Static files from React Vite dist (Production unified server)
        else:
            rel_path = path.lstrip("/")
            if not rel_path or rel_path == "":
                rel_path = "index.html"
            local_file = os.path.join(DIST_DIR, rel_path)

            if os.path.isfile(local_file):
                mime = "text/html"
                if local_file.endswith(".js"):
                    mime = "text/javascript"
                elif local_file.endswith(".css"):
                    mime = "text/css"
                elif local_file.endswith(".svg"):
                    mime = "image/svg+xml"
                elif local_file.endswith(".png"):
                    mime = "image/png"
                elif local_file.endswith(".jpg"):
                    mime = "image/jpeg"
                self._set_cors_headers(mime)
                self.end_headers()
                with open(local_file, "rb") as f:
                    self.wfile.write(f.read())
            elif os.path.isfile(os.path.join(DIST_DIR, "index.html")):
                self._set_cors_headers("text/html")
                self.end_headers()
                with open(os.path.join(DIST_DIR, "index.html"), "rb") as f:
                    self.wfile.write(f.read())
            else:
                self._set_cors_headers("application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "message": "OpenCV Live Analytics API",
                    "endpoints": [
                        "/api/telemetry",
                        "/api/stream",
                        "/api/snapshot",
                        "/api/refresh",
                        "/api/status"
                    ]
                }).encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_server(port=PORT):
    server = ThreadedHTTPServer(("0.0.0.0", port), AnalyticsAPIHandler)
    print("\n" + "=" * 65)
    print("      OPENCV LIVE ANALYTICS - PYTHON MIDDLE-LAYER SERVER")
    print("=" * 65)
    print(f"[+] API Server listening on: http://localhost:{port}")
    print(f"[+] Telemetry Feed:           http://localhost:{port}/api/telemetry")
    print(f"[+] Real-time SSE Stream:     http://localhost:{port}/api/stream")
    print(f"[+] Live Snapshot Preview:    http://localhost:{port}/api/snapshot")
    print(f"[+] Refresh Frame Endpoint:   http://localhost:{port}/api/refresh")
    print(f"[+] Server Health / Status:   http://localhost:{port}/api/status")
    print("=" * 65)
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping server...")
    finally:
        server.server_close()
        print("[+] Server stopped cleanly.")


if __name__ == "__main__":
    start_server()
