import os
import sys
import time
import json
import subprocess
import threading
import uuid
import requests
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from pymongo import MongoClient
from dotenv import load_dotenv

# --- Platform Specific Configuration ---
if getattr(sys, "frozen", False) and sys.stdout is None:
    _log_path = Path.home() / "Library/Logs/TrackFlow/agent.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout

# Load .env
_env_candidates = [Path(".env"), Path("../.env"), Path("../backend/.env")]
if getattr(sys, "frozen", False):
    _env_candidates.insert(0, Path(sys._MEIPASS) / ".env")
for path in _env_candidates:
    if path.exists():
        load_dotenv(path)
        break

APPDATA_PATH = Path.home() / "Library/Application Support/TrackFlow"
APPDATA_PATH.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = APPDATA_PATH / "agent_config.json"
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB", "tracker")

# --- Proxy Handler (Feature Parity with Windows) ---
class LocalProxyHandler(BaseHTTPRequestHandler):
    tracker = None

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Machine-GUID')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            payload = json.loads(post_data)
            path = self.path.rstrip('/')
            machine_guid = self.tracker.machine_id if self.tracker else ""
            payload["device_id"] = machine_guid

            collection_map = {
                "/api/v1/context/editor": "editor_context",
                "/api/v1/context/browser": "browser_context",
                "/api/v1/context/app": "app_context",
                "/api/v1/events": "events",
                "/api/v1/idle": "idle_periods"
            }
            collection_name = collection_map.get(path)
            
            if self.tracker and self.tracker.db is not None and collection_name:
                self.tracker.db[collection_name].insert_one(payload)
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"message":"proxied"}')
            else:
                self.send_response(502)
                self.end_headers()
        except:
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args): return

# --- Main Tracker ---
def get_macos_active_window():
    script = 'tell application "System Events" to get {name, title} of first application process whose frontmost is true'
    try:
        proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if proc.returncode == 0:
            parts = proc.stdout.strip().split(', ')
            return parts[0], parts[1] if len(parts) > 1 else ""
    except: pass
    return "Unknown", ""

class MacTracker:
    def __init__(self):
        self.machine_id = self.get_machine_id()
        self.db = None
        self.connect_mongodb()
        self.start_proxy()
        self.running = True

    def get_machine_id(self):
        try: return subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID", shell=True).decode().split('"')[-2]
        except: return f"mac-{uuid.getnode()}"

    def connect_mongodb(self):
        if MONGODB_URI:
            try:
                self.client = MongoClient(MONGODB_URI)
                self.db = self.client[MONGODB_DB_NAME]
            except: pass

    def start_proxy(self):
        LocalProxyHandler.tracker = self
        def run_server():
            server_address = ('127.0.0.1', 10101)
            httpd = HTTPServer(server_address, LocalProxyHandler)
            httpd.serve_forever()
        threading.Thread(target=run_server, daemon=True).start()

    def run(self):
        print(f"TrackFlow Agent (macOS) ready. Machine: {self.machine_id}")
        while self.running:
            # Active window polling and classification logic here...
            time.sleep(2)

if __name__ == "__main__":
    MacTracker().run()
