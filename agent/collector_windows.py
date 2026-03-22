from __future__ import annotations

import ctypes
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Fix stdout/stderr for PyInstaller --noconsole mode (Windows sets them to None)
if getattr(sys, "frozen", False) and sys.stdout is None:
    _log_path = Path(os.getenv("APPDATA", Path.home() / "AppData/Roaming")) / "TrackFlow" / "agent.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
    sys.stdout = _log_file
    sys.stderr = _log_file

import psutil
import requests
import pymongo
from pymongo import MongoClient
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import shutil
import subprocess
import uuid
import winreg
import tkinter as tk
from tkinter import simpledialog, messagebox
from dotenv import load_dotenv

# Try to load .env from several likely locations
_env_candidates = [Path(".env"), Path("../.env"), Path("../backend/.env")]
if getattr(sys, "frozen", False):
    _env_candidates.insert(0, Path(sys._MEIPASS) / ".env")
for path in _env_candidates:
    if path.exists():
        load_dotenv(path)
        break

# USER32 and KERNEL32 will be initialized inside the class for better scope reliability.

def gui_input(title, prompt, default=""):
    """Prompt the user for input using a GUI dialog."""
    root = tk.Tk()
    root.withdraw()  # Hide main window
    # Ensure it comes to foreground
    root.attributes("-topmost", True)
    result = simpledialog.askstring(title, prompt, initialvalue=default)
    root.destroy()
    return result

def gui_alert(title, message, is_error=False):
    """Show a GUI alert message."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    if is_error:
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)
    root.destroy()

# Production paths: Store in %APPDATA%\TrackFlow
APPDATA_PATH = Path(os.getenv("APPDATA", Path.home() / "AppData/Roaming")) / "TrackFlow"
APPDATA_PATH.mkdir(parents=True, exist_ok=True)

API_BASE_URL = os.getenv("TRACKER_API_BASE_URL", "http://127.0.0.1:10101")
CONFIG_PATH = APPDATA_PATH / "agent_config.json"

POLL_SECONDS = float(os.getenv("TRACKER_POLL_SECONDS", "2"))
MAX_SEGMENT_SECONDS = int(os.getenv("TRACKER_MAX_SEGMENT_SECONDS", "20"))
IDLE_THRESHOLD_SECONDS = int(os.getenv("TRACKER_IDLE_THRESHOLD_SECONDS", "300"))
TITLE_MAX_LENGTH = int(os.getenv("TRACKER_TITLE_MAX_LENGTH", "300"))
SOURCE_NAME = os.getenv("TRACKER_SOURCE_NAME", "windows_agent")
RULES_PATH = Path(os.getenv("TRACKER_RULES_PATH", APPDATA_PATH / "productivity_rules.json"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("TRACKER_REQUEST_TIMEOUT_SECONDS", "10"))
REGISTRATION_TOKEN = os.getenv("TRACKER_REGISTRATION_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME") or os.getenv("MONGODB_DB", "tracker")

PROCESS_ALIASES = {
    "code.exe": "VS Code",
    "cursor.exe": "Cursor",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "brave.exe": "Brave",
    "firefox.exe": "Firefox",
    "slack.exe": "Slack",
    "outlook.exe": "Outlook",
    "teams.exe": "Microsoft Teams",
    "excel.exe": "Excel",
    "winword.exe": "Word",
    "powerpnt.exe": "PowerPoint",
    "notion.exe": "Notion",
    "spotify.exe": "Spotify",
    "photoshop.exe": "Photoshop",
    "adobe premiere pro.exe": "Premiere Pro",
    "afterfx.exe": "After Effects",
    "illustrator.exe": "Illustrator",
    "resolve.exe": "DaVinci Resolve",
    "antigravity.exe": "Antigravity",
}

DEFAULT_RULES: dict[str, list[str]] = {
    "productive_processes": [
        "code.exe",
        "cursor.exe",
        "pycharm64.exe",
        "idea64.exe",
        "devenv.exe",
        "notion.exe",
        "excel.exe",
        "winword.exe",
        "powerpnt.exe",
        "obsidian.exe",
        "postman.exe",
        "docker desktop.exe",
        "figma.exe",
        "photoshop.exe",
        "adobe premiere pro.exe",
        "afterfx.exe",
        "illustrator.exe",
        "resolve.exe",
        "antigravity.exe",
        "windsurf.exe",
        "webstorm64.exe"
    ],
    "neutral_processes": [
        "slack.exe",
        "outlook.exe",
        "teams.exe",
        "zoom.exe",
        "telegram.exe",
        "whatsapp.exe",
        "explorer.exe",
        "cmd.exe",
        "powershell.exe",
        "windowsterminal.exe",
        "spotify.exe",  # music while working = neutral, not distracting
    ],
    "distracting_processes": [
        "vlc.exe",
        "steam.exe",
        "epicgameslauncher.exe",
        "discord.exe",
    ],
    # NOTE: productive keywords are checked FIRST — they always win over distracting.
    # This means "YouTube - How to Learn Python" -> productive (tutorial wins over youtube).
    "productive_title_keywords": [
        # Dev / Code
        "github", "gitlab", "bitbucket", "jira", "linear", "notion", "confluence",
        "documentation", "docs", "readme", "spreadsheet", "budget", "proposal",
        "research", "figma", "dashboard", "report", "fastapi", "react", "python",
        "javascript", "typescript", "nodejs", "node.js", "sql", "backend", "frontend",
        "system design", "algorithm", "api", "docker", "kubernetes", "ci/cd", "devops",
        "antigravity", "vscode", "vs code", "stackoverflow", "mdn web docs",
        # AI / ML / LLM
        "machine learning", "deep learning", "neural network", "large language model",
        "llm", "gpt", "gemini", "claude", "mistral", "llama", "transformer", "bert",
        "fine-tuning", "rag", "retrieval augmented", "embedding", "vector database",
        "langchain", "hugging face", "pytorch", "tensorflow", "keras", "scikit-learn",
        "nlp", "natural language processing", "computer vision", "prompt engineering",
        "reinforcement learning", "stable diffusion", "openai", "anthropic",
        # Data Science
        "data science", "data analysis", "pandas", "numpy", "jupyter", "notebook",
        "data pipeline", "etl", "statistics", "regression", "classification",
        # Cloud
        "aws", "google cloud", "gcp", "azure", "cloudflare", "vercel", "serverless",
        # Learning
        "tutorial", "how to", "learn", "course", "lecture", "explained",
        "fundamentals", "masterclass", "coursera", "udemy", "freecodecamp",
        "leetcode", "hackerrank", "ted talk", "ted-ed", "book summary",
        "lok sabha", "budget", "proposal", "research", "figma", "dashboard", "report","rajya sabha",
        "antigravity", "vscode", "vs code", "stackoverflow", "mdn web docs",
    ],
    "neutral_title_keywords": [
        "slack", "gmail", "calendar", "meet", "zoom", "teams", "mail", "inbox",
        "outlook", "whatsapp", "telegram", "wikipedia", "google search", "translate",
    ],
    # NOTE: 'youtube' is NOT in this list — YouTube videos are classified by content.
    # A video with 'tutorial' in the title gets caught by productive_title_keywords first.
    "distracting_title_keywords": [
        # YouTube — content-specific signals only
        "shorts", "vlog", "reaction", "try not to laugh", "meme", "funny",
        "roast", "prank", "challenge", "satisfying", "asmr", "music video",
        "official video", "lyric video", "live concert", "unboxing", "haul",
        "top 10", "viral", "celebrity", "gossip",
        # Streaming
        "netflix", "prime video", "amazon prime", "hotstar", "disney+", "spotify",
        "crunchyroll", "watch online", "full movie", "full episode",
        # Social media
        "instagram", "facebook", "x.com", "twitter", "tiktok", "snapchat", "reddit",
        # Gaming
        "steam", "epic games", "gaming", "playthrough", "speedrun",
        "esports", "roblox", "minecraft", "fortnite", "valorant",
        # Entertainment
        "playlist", "trending", "songs", "bollywood", "web series",
    ],
}

BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe"}


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


@dataclass(slots=True)
class WindowSnapshot:
    app_name: str
    process_name: str
    window_title: str
    url: str | None
    category: str | None
    productivity_label: str

    def same_context(self, other: "WindowSnapshot") -> bool:
        return (
            self.process_name == other.process_name
            and self.window_title == other.window_title
            and self.productivity_label == other.productivity_label
        )


@dataclass(slots=True)
class OpenActivity:
    snapshot: WindowSnapshot
    started_at: datetime


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

            # Add device info
            machine_guid = self.tracker.machine_guid if self.tracker else self.headers.get('X-Machine-GUID', '')
            payload["device_id"] = machine_guid
            payload["machine_guid"] = machine_guid

            # Map paths to collections
            collection_map = {
                "/api/v1/context/editor": "editor_context",
                "/api/v1/context/browser": "browser_context",
                "/api/v1/context/app": "app_context",
                "/api/v1/events": "events",
                "/api/v1/idle": "idle_periods"
            }

            collection_name = collection_map.get(path)
            if not collection_name:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

            # Convert ISO strings to naive LOCAL datetime objects for MongoDB
            # Also store the original local time string for direct display
            for key in ["captured_at", "started_at", "ended_at"]:
                if key in payload and isinstance(payload[key], str):
                    raw_str = payload[key]
                    try:
                        # Parse the ISO string
                        if 'Z' in raw_str or '+' in raw_str[10:]:
                            # UTC or timezone-aware — convert to local
                            dt = datetime.fromisoformat(raw_str.replace('Z', '+00:00'))
                            dt = dt.astimezone()  # to system local
                            dt = dt.replace(tzinfo=None)
                        else:
                            # Already local naive time from extension
                            dt = datetime.fromisoformat(raw_str)
                        payload[key] = dt
                        # Store display string — full ISO local time for frontend parsing
                        payload[f"{key}_str"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
                    except:
                        pass

            # Build fallback payload NOW — before insert_one() can mutate the dict with _id
            # Use a custom serializer so datetimes and any stray ObjectIds are safely encoded
            def _proxy_json_default(obj):
                if isinstance(obj, datetime):
                    return obj.strftime("%Y-%m-%dT%H:%M:%S")
                return str(obj)  # handles ObjectId, bytes, and any other non-serializable type

            fallback_body = json.dumps(payload, default=_proxy_json_default).encode()

            def _send_ok():
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"message": "proxied to mongodb"}).encode())

            def _send_response_safe(status, content=None):
                try:
                    self.send_response(status)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    if content:
                        self.wfile.write(content)
                except OSError:
                    pass  # Client disconnected — socket errors on Windows are all OSError

            # Fast path: direct MongoDB insert
            if self.tracker and self.tracker.db is not None:
                try:
                    self.tracker.db[collection_name].insert_one(payload)
                    try:
                        _send_ok()
                    except OSError:
                        pass  # Client timed out — data was saved to MongoDB, ignore
                    return
                except Exception as mongo_err:
                    print(f"MongoDB insert failed, falling back to API: {mongo_err}")
                    # Mark connection as dead so health check reconnects
                    self.tracker.db = None
                    self.tracker.client = None

            # Fallback: forward to backend API at port 8080 using pre-built JSON body
            try:
                resp = requests.post(
                    f"http://127.0.0.1:8080{path}",
                    data=fallback_body,
                    headers={"X-Machine-GUID": machine_guid, "Content-Type": "application/json"},
                    timeout=5
                )
                _send_response_safe(resp.status_code, resp.content)
            except Exception as fwd_err:
                print(f"Proxy fallback error: {fwd_err}")
                _send_response_safe(502)
        except OSError:
            pass  # Client disconnected — all Windows socket errors are OSError subclasses
        except Exception as e:
            print(f"Proxy error: {e}")
            try:
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
            except OSError:
                pass

    def log_message(self, format, *args):
        # Suppress logging for every request
        return


class ProductivityRules:
    def __init__(self, rules: dict[str, list[str]]) -> None:
        self.rules = {key: [self._normalize(item) for item in values] for key, values in rules.items()}

    @staticmethod
    def _normalize(value: str | None) -> str:
        return (value or "").strip().lower()

    @classmethod
    def load(cls, path: Path) -> "ProductivityRules":
        if not path.exists():
            return cls(DEFAULT_RULES)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Deep merge lists instead of replacing keys
            merged = DEFAULT_RULES.copy()
            for key, value in data.items():
                if isinstance(value, list) and key in merged:
                    # Combine existing list with new items, keeping unique entries
                    merged[key] = list(set(merged[key] + value))
                else:
                    merged[key] = value
            return cls(merged)
        except Exception as e:
            print(f"Warning: Failed to load rules from {path}: {e}")
            return cls(DEFAULT_RULES)

    def classify(self, process_name: str, title: str) -> tuple[str, str | None]:
        proc = self._normalize(process_name)
        title_norm = self._normalize(title)

        if proc in self.rules["productive_processes"]:
            return "productive", "app_rule"
        if proc in self.rules["neutral_processes"]:
            return "neutral", "app_rule"
        if proc in self.rules["distracting_processes"]:
            return "distracting", "app_rule"

        if proc in BROWSER_PROCESSES:
            label = self._classify_by_keywords(title_norm)
            if label:
                return label, "browser_title_rule"
            return "neutral", "browser_fallback"

        label = self._classify_by_keywords(title_norm)
        if label:
            return label, "title_rule"

        return "neutral", "default"

    def _classify_by_keywords(self, title_norm: str) -> str | None:
        for keyword in self.rules["productive_title_keywords"]:
            if keyword in title_norm:
                return "productive"
        for keyword in self.rules["neutral_title_keywords"]:
            if keyword in title_norm:
                return "neutral"
        for keyword in self.rules["distracting_title_keywords"]:
            if keyword in title_norm:
                return "distracting"
        return None


class WindowsTracker:
    def __init__(self) -> None:
        self.USER32 = ctypes.windll.user32
        self.KERNEL32 = ctypes.windll.kernel32
        
        self.session = requests.Session()
        self.machine_guid = self.get_machine_guid()
        
        self.api_base_url = API_BASE_URL
        self.mongodb_uri = MONGODB_URI or os.getenv("MONGODB_URI")
        self.mongodb_db_name = MONGODB_DB_NAME or os.getenv("MONGODB_DB", "tracker")
        
        self.ensure_registered()
        self.add_to_startup()
        self.install_extensions()

        # MongoDB Connection
        self.client = None
        self.db = None
        self.connect_mongodb()
        
        # Start Local Proxy
        self.start_proxy()
        
        self.rules = ProductivityRules.load(RULES_PATH)
        self.current_activity: OpenActivity | None = None
        self.idle_started_at: datetime | None = None
        self.running = True

    def connect_mongodb(self):
        if not self.mongodb_uri:
            print("Warning: MONGODB_URI not found. Agent will not be able to write directly.")
            return
        try:
            self.client = MongoClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            # Verify connection is actually alive
            self.client.admin.command('ping')
            self.db = self.client[self.mongodb_db_name]
            print(f"Connected to MongoDB: {self.mongodb_db_name}")
        except Exception as e:
            print(f"Error connecting to MongoDB: {e}")
            self.client = None
            self.db = None

    def start_proxy(self):
        LocalProxyHandler.tracker = self
        def run_server():
            server_address = ('127.0.0.1', 10101)
            try:
                class _ReuseHTTPServer(HTTPServer):
                    allow_reuse_address = True
                httpd = _ReuseHTTPServer(server_address, LocalProxyHandler)
                print("Local Proxy listening on 127.0.0.1:10101")
                httpd.serve_forever()
            except Exception as e:
                print(f"Failed to start local proxy: {e}")

        self.proxy_thread = threading.Thread(target=run_server, daemon=True)
        self.proxy_thread.start()

    @staticmethod
    def get_machine_guid() -> str:
        """Retrieve the Windows Machine GUID from the registry."""
        try:
            cmd = 'reg query "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid'
            output = subprocess.check_output(cmd, shell=True).decode()
            for line in output.splitlines():
                if "MachineGuid" in line:
                    return line.split()[-1]
        except Exception as e:
            print(f"Warning: Failed to get Machine GUID: {e}")
        
        # Fallback to a stable ID based on local data if registry fails
        fallback_id = str(uuid.getnode())
        return f"fallback-{fallback_id}"

    def ensure_registered(self) -> None:
        """Simple check if we already have the necessary info."""
        if CONFIG_PATH.exists():
            try:
                config = json.loads(CONFIG_PATH.read_text())
                if config.get("machine_guid") == self.machine_guid:
                    self.api_base_url = config.get("api_base_url", self.api_base_url)
                    self.mongodb_uri = config.get("mongodb_uri", self.mongodb_uri)
                    self.mongodb_db_name = config.get("mongodb_db_name", self.mongodb_db_name)
                    print("Registration config loaded.")
                    return
            except:
                pass

        # First launch — show registration dialog
        self.show_registration_dialog()

    def show_registration_dialog(self) -> None:
        """Show first-launch dialog for device registration."""
        result = {"token": None, "mode": None}

        root = tk.Tk()
        root.title("TrackFlow Agent Setup")
        root.geometry("420x280")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="#1a1a2e")

        try:
            root.eval('tk::PlaceWindow . center')
        except:
            pass

        tk.Label(root, text="Welcome to TrackFlow", font=("Segoe UI", 16, "bold"),
                 bg="#1a1a2e", fg="white").pack(pady=(24, 4))
        tk.Label(root, text="How would you like to register this device?",
                 font=("Segoe UI", 10), bg="#1a1a2e", fg="#aaaaaa").pack(pady=(0, 24))

        def with_token():
            result["mode"] = "token"
            root.destroy()

        def without_token():
            result["mode"] = "no_token"
            root.destroy()

        btn_frame = tk.Frame(root, bg="#1a1a2e")
        btn_frame.pack(pady=4)

        tk.Button(btn_frame, text="🔑  I Have a Token", command=with_token,
                  width=28, height=2, font=("Segoe UI", 10),
                  bg="#6c5ce7", fg="white", relief="flat", cursor="hand2").pack(pady=6)
        tk.Button(btn_frame, text="Register Without Token", command=without_token,
                  width=28, height=2, font=("Segoe UI", 10),
                  bg="#2d2d44", fg="#cccccc", relief="flat", cursor="hand2").pack(pady=6)

        root.protocol("WM_DELETE_WINDOW", without_token)
        root.mainloop()

        # After dialog closes, handle the result
        if result["mode"] == "token":
            token = gui_input("Enter Token", "Paste the registration token from your admin:")
            if token and token.strip():
                success = self.perform_registration(token=token.strip())
                if success:
                    gui_alert("TrackFlow", "Device registered and linked successfully!\nTracking will begin automatically.")
                else:
                    gui_alert("TrackFlow", "Invalid token or server unreachable.\nDevice registered without assignment — your admin can assign it from the dashboard.", is_error=True)
                    self.perform_registration()  # Fallback: register without token
            else:
                self.perform_registration()
                gui_alert("TrackFlow", "Device registered without token.\nYour admin will assign this device from the dashboard.")
        else:
            # Ask for name and email for tokenless registration
            name = gui_input("TrackFlow Setup", "Enter your full name:")
            email = gui_input("TrackFlow Setup", "Enter your email address:")
            success = self.perform_registration(full_name=name, email=email)
            if success:
                gui_alert("TrackFlow", f"Device registered as {name}!\nTracking will begin automatically.")
            else:
                gui_alert("TrackFlow", "Device registered.\nYour admin will assign this device from the dashboard.")

    def perform_registration(self, token: str | None = None, full_name: str | None = None, email: str | None = None) -> bool:
        """Report Machine GUID to backend and get assignment if available."""
        # Use backend server directly (port 8080) — local proxy (10101) hasn't started yet
        register_url = os.getenv("TRACKER_SERVER_URL", "http://127.0.0.1:8080")
        payload = {
            "machine_guid": self.machine_guid,
            "os_type": "windows",
            "registration_token": token or REGISTRATION_TOKEN,
        }
        if full_name:
            payload["full_name"] = full_name
        if email:
            payload["email"] = email

        # Retry — server may still be starting (Electron launches both EXEs simultaneously)
        for attempt in range(5):
            try:
                resp = self.session.post(
                    f"{register_url.rstrip('/')}/api/v1/register",
                    json=payload,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Always save mongodb_uri if returned (server now always returns it)
                    if data.get("mongodb_uri"):
                        self.mongodb_uri = data["mongodb_uri"]
                        self.mongodb_db_name = data.get("mongodb_db", self.mongodb_db_name)
                    # Save config to disk so next launch doesn't re-register
                    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    CONFIG_PATH.write_text(json.dumps({
                        "machine_guid": self.machine_guid,
                        "api_base_url": self.api_base_url,
                        "mongodb_uri": self.mongodb_uri,
                        "mongodb_db_name": self.mongodb_db_name
                    }))
                    if data.get("assigned_user"):
                        print(f"Device assigned to {data['assigned_user']}")
                        return True
                    else:
                        print("Device registered. MongoDB URI saved. Waiting for admin assignment...")
                        return False
                elif resp.status_code == 401:
                    print("Invalid registration token.")
                    return False
                else:
                    print(f"Registration failed (Status {resp.status_code})")
                    return False
            except requests.ConnectionError:
                print(f"Server not ready, retrying... ({attempt + 1}/5)")
                if attempt < 4:
                    time.sleep(2)
            except Exception as e:
                print(f"Registration error: {e}")
                return False
        print("Could not connect to server after 5 attempts.")
        return False

    def add_to_startup(self) -> None:
        """Add the app to Windows Startup registry."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "TrackFlowAgent"
        try:
            # Get absolute path of current script or exe
            script_path = os.path.abspath(sys.argv[0])
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{script_path}"')
            winreg.CloseKey(key)
            print(f"Added to startup: {script_path}")
        except Exception as e:
            print(f"Warning: Failed to add to startup: {e}")

    # ------------------------------------------------------------------
    # Auto-install extensions (runs once on first install)
    # ------------------------------------------------------------------

    def _extensions_installed(self) -> bool:
        """Check if extensions have already been installed."""
        flag_file = APPDATA_PATH / ".extensions_installed"
        return flag_file.exists()

    def _mark_extensions_installed(self) -> None:
        """Mark extensions as installed so we don't re-run."""
        flag_file = APPDATA_PATH / ".extensions_installed"
        flag_file.write_text(datetime.now().isoformat())

    def install_extensions(self) -> None:
        """Auto-install editor and browser extensions on first run."""
        if self._extensions_installed():
            return
        print("First run detected — installing extensions...")
        self.install_editor_extensions()
        self.install_browser_extensions()
        self._mark_extensions_installed()
        print("Extension installation complete.")

    @staticmethod
    def _bundle_dir() -> Path:
        """Return the directory where PyInstaller extracts bundled data files.
        Falls back to the directory containing the script in dev mode."""
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS)
        return Path(__file__).parent

    def install_editor_extensions(self) -> None:
        """Auto-install TrackFlow VSIX into detected VS Code-compatible editors."""
        # PyInstaller extracts bundled data to _MEIPASS; in dev mode use script dir
        vsix_path = self._bundle_dir() / "trackflow-context-0.0.1.vsix"
        if not vsix_path.exists():
            # Also check next to the EXE itself
            vsix_path = Path(sys.argv[0]).parent / "trackflow-context-0.0.1.vsix"
        if not vsix_path.exists():
            print("VSIX not found, skipping editor extension install")
            return

        editors = {
            "VS Code": "code",
            "Cursor": "cursor",
            "Antigravity": "antigravity",
        }
        for name, cli in editors.items():
            try:
                result = subprocess.run(
                    [cli, "--install-extension", str(vsix_path)],
                    capture_output=True, timeout=60, text=True,
                )
                if result.returncode == 0:
                    print(f"Installed TrackFlow extension in {name}")
                else:
                    print(f"{name}: install returned code {result.returncode}")
            except FileNotFoundError:
                # Editor CLI not found — editor not installed, skip silently
                pass
            except Exception as e:
                print(f"Failed to install extension in {name}: {e}")

    def install_browser_extensions(self) -> None:
        """Auto-install Chrome/Brave extension via Windows registry policy."""
        # Locate extension source files (bundled by PyInstaller or in dev tree)
        ext_source = self._bundle_dir() / "chrome-extension"
        if not ext_source.exists():
            ext_source = Path(__file__).parent.parent / "chrome-extension"
        if not ext_source.exists():
            print("Chrome extension source not found, skipping browser install")
            return

        # Copy extension to persistent location in AppData
        dest = APPDATA_PATH / "chrome-extension"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ext_source, dest)
        print(f"Copied browser extension to {dest}")

        # Generate update manifest for the extension
        update_manifest = dest / "update.xml"
        update_manifest.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">\n'
            "  <app appid=\"trackflow-browser-context\">\n"
            '    <updatecheck codebase="file:///' + str(dest).replace("\\", "/") + '/"\n'
            '                 version="0.0.1" />\n'
            "  </app>\n"
            "</gupdate>\n"
        )

        # Register via Windows registry for Chrome and Brave
        browsers = {
            "Chrome": r"Software\Policies\Google\Chrome",
            "Brave": r"Software\Policies\BraveSoftware\Brave",
        }

        dest_posix = str(dest).replace("\\", "/")

        for name, base_key in browsers.items():
            try:
                # 1) Allow dev-mode extensions
                self._reg_set_dword(
                    winreg.HKEY_LOCAL_MACHINE,
                    base_key,
                    "DeveloperToolsAvailability",
                    1,
                )

                # 2) Allow loading unpacked from our path
                self._reg_set_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    base_key + r"\ExtensionInstallSources",
                    "1",
                    f"file:///{dest_posix}/*",
                )

                # 3) Whitelist the extension install
                self._reg_set_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    base_key + r"\ExtensionInstallAllowedTypes",
                    "1",
                    "extension",
                )

                print(f"Registered extension policy for {name}")
            except PermissionError:
                # No admin rights — try HKCU as fallback
                try:
                    self._reg_set_string(
                        winreg.HKEY_CURRENT_USER,
                        base_key + r"\ExtensionInstallSources",
                        "1",
                        f"file:///{dest_posix}/*",
                    )
                    print(f"Registered extension source for {name} (user-level)")
                except Exception as e2:
                    print(f"Cannot write registry for {name}: {e2}")
            except Exception as e:
                print(f"Failed to register extension for {name}: {e}")

    @staticmethod
    def _reg_set_string(root, key_path: str, name: str, value: str) -> None:
        key = winreg.CreateKey(root, key_path)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)

    @staticmethod
    def _reg_set_dword(root, key_path: str, name: str, value: int) -> None:
        key = winreg.CreateKey(root, key_path)
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
        winreg.CloseKey(key)

    def run(self) -> None:
        self._register_signal_handlers()
        self._last_health_check = time.time()
        print(
            f"Starting Windows tracker. API={API_BASE_URL} poll={POLL_SECONDS}s "
            f"idle_threshold={IDLE_THRESHOLD_SECONDS}s max_segment={MAX_SEGMENT_SECONDS}s"
        )
        print(f"Rules file: {RULES_PATH}")

        while self.running:
            # Periodic MongoDB health check (every 60 seconds)
            if self.db is not None and time.time() - self._last_health_check > 60:
                self._last_health_check = time.time()
                try:
                    self.client.admin.command('ping')
                except Exception as e:
                    print(f"MongoDB health check failed, will reconnect: {e}")
                    self.db = None
                    self.client = None

            # If not connected to MongoDB, keep trying to register/discover
            if self.db is None:
                self.perform_registration()
                self.connect_mongodb()
                if self.db is None:
                    time.sleep(10) # Wait longer if not assigned
                    continue

            now = datetime.now().replace(microsecond=0)
            try:
                idle_seconds = self.get_idle_seconds()
                if idle_seconds >= IDLE_THRESHOLD_SECONDS:
                    self.handle_idle(now, idle_seconds)
                else:
                    self.handle_active(now)
            except requests.RequestException as exc:
                print(f"Network error: {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"Unexpected collector error: {exc}")

            time.sleep(POLL_SECONDS)

        self.shutdown()

    def _register_signal_handlers(self) -> None:
        def _stop(*_: Any) -> None:
            self.running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

    def handle_idle(self, now: datetime, idle_seconds: float) -> None:
        idle_started_at = now - timedelta(seconds=int(idle_seconds))
        if self.current_activity is not None:
            event_end = max(self.current_activity.started_at, idle_started_at)
            self.post_event(self.current_activity.snapshot, self.current_activity.started_at, event_end)
            self.current_activity = None

        if self.idle_started_at is None:
            self.idle_started_at = idle_started_at
            print(f"Idle detected from {self.idle_started_at.isoformat(sep=' ')}")

    def handle_active(self, now: datetime) -> None:
        if self.idle_started_at is not None:
            self.post_idle_period(self.idle_started_at, now)
            print(f"Idle ended at {now.isoformat(sep=' ')}")
            self.idle_started_at = None

        snapshot = self.capture_snapshot()
        if snapshot is None:
            return

        if self.current_activity is None:
            self.current_activity = OpenActivity(snapshot=snapshot, started_at=now)
            print(f"Tracking started: {snapshot.app_name} | {snapshot.window_title}")
            return

        current = self.current_activity
        segment_age = int((now - current.started_at).total_seconds())
        should_flush = not current.snapshot.same_context(snapshot) or segment_age >= MAX_SEGMENT_SECONDS
        if not should_flush:
            return

        self.post_event(current.snapshot, current.started_at, now)
        self.current_activity = OpenActivity(snapshot=snapshot, started_at=now)
        print(f"Tracking switched: {snapshot.app_name} | {snapshot.window_title}")

    def shutdown(self) -> None:
        now = datetime.now().replace(microsecond=0)
        if self.current_activity is not None:
            self.post_event(self.current_activity.snapshot, self.current_activity.started_at, now)
            self.current_activity = None
        if self.idle_started_at is not None and now > self.idle_started_at:
            self.post_idle_period(self.idle_started_at, now)
            self.idle_started_at = None
        print("Tracker stopped.")

    def capture_snapshot(self) -> WindowSnapshot | None:
        hwnd = self.USER32.GetForegroundWindow()
        if not hwnd:
            return None

        title = self.get_window_title(hwnd)
        if not title:
            return None

        pid = ctypes.c_ulong()
        self.USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = self.get_process_name(pid.value)
        process_lower = process_name.lower()
        
        app_name = PROCESS_ALIASES.get(process_lower, Path(process_name).stem or process_name or "Unknown")
        app_name = app_name if app_name else "Unknown"

        # Special handling for Creative Apps (DaVinci, Adobe)
        # Goal: Extract "Project Name" or "File Name" from the messy window title.
        project_name = None
        if "resolve.exe" in process_lower:
            # Format: "DaVinci Resolve - ProjectName - TimelineName"
            if " - " in title:
                parts = title.split(" - ")
                if len(parts) >= 2:
                    project_name = parts[1].strip()
        elif "photoshop.exe" in process_lower:
            # Format: "filename.psd @ 100% (Layer, Mode) *"
            if " @ " in title:
                project_name = title.split(" @ ")[0].strip()
        elif "adobe premiere pro" in process_lower:
            # Format: "Adobe Premiere Pro 2024 - C:\path\to\proj.prproj"
            if " - " in title:
                project_name = Path(title.split(" - ")[-1].strip()).name
        elif "illustrator.exe" in process_lower:
            # Format: "Project.ai @ 66.67% (RGB/Preview) *"
            if " @ " in title:
                project_name = title.split(" @ ")[0].strip()

        # If we extracted a cleaner project name, we can use it or append it
        display_title = title
        if project_name:
            display_title = f"[{project_name}] {title}"

        productivity_label, category = self.rules.classify(process_name, title)

        return WindowSnapshot(
            app_name=app_name,
            process_name=process_lower,
            window_title=display_title[:TITLE_MAX_LENGTH],
            url=None,
            category=category,
            productivity_label=productivity_label,
        )

    def get_window_title(self, hwnd: int) -> str:
        length = self.USER32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.USER32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value.strip()

    @staticmethod
    def get_process_name(pid: int) -> str:
        if pid <= 0:
            return "unknown.exe"
        try:
            return psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "unknown.exe"

    def get_idle_seconds(self) -> float:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not self.USER32.GetLastInputInfo(ctypes.byref(info)):
            raise ctypes.WinError()
        millis_since_last_input = self.KERNEL32.GetTickCount() - info.dwTime
        return max(millis_since_last_input / 1000.0, 0.0)

    def post_event(self, snapshot: WindowSnapshot, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            return
            
        payload = {
            "device_id": self.machine_guid,
            "machine_guid": self.machine_guid,
            "started_at": started_at,
            "ended_at": ended_at,
            "app_name": snapshot.app_name,
            "window_title": snapshot.window_title,
            "url": snapshot.url,
            "category": snapshot.category,
            "productivity_label": snapshot.productivity_label,
            "notes": json.dumps(
                {
                    "process_name": snapshot.process_name,
                    "classification_source": snapshot.category,
                }
            ),
            "source": SOURCE_NAME,
        }
        
        if self.db is not None:
            try:
                self.db.events.insert_one(payload)
                print(
                    f"Event saved to MongoDB: {snapshot.app_name} | {snapshot.productivity_label} | "
                    f"{started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}"
                )
                return
            except Exception as e:
                print(f"MongoDB event insert failed, marking for reconnect: {e}")
                self.db = None
                self.client = None

        # Fallback: send via API
        try:
            fallback_payload = {
                k: v.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(v, datetime) else v
                for k, v in payload.items()
            }
            self.session.post(
                "http://127.0.0.1:8080/api/v1/events",
                json=fallback_payload,
                headers={"X-Machine-GUID": self.machine_guid, "Content-Type": "application/json"},
                timeout=5
            )
            print(f"Event saved via API fallback: {snapshot.app_name}")
        except Exception as fwd_err:
            print(f"Warning: Could not save event (MongoDB down, API fallback failed): {fwd_err}")

    def post_idle_period(self, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            return
        payload = {
            "device_id": self.machine_guid,
            "machine_guid": self.machine_guid,
            "started_at": started_at,
            "ended_at": ended_at,
            "reason": "idle",
        }
        if self.db is not None:
            try:
                self.db.idle_periods.insert_one(payload)
                print(f"Idle period saved to MongoDB: {started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}")
                return
            except Exception as e:
                print(f"MongoDB idle insert failed, marking for reconnect: {e}")
                self.db = None
                self.client = None

        # Fallback: send via API
        try:
            fallback_payload = {
                k: v.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(v, datetime) else v
                for k, v in payload.items()
            }
            self.session.post(
                "http://127.0.0.1:8080/api/v1/idle",
                json=fallback_payload,
                headers={"X-Machine-GUID": self.machine_guid, "Content-Type": "application/json"},
                timeout=5
            )
            print(f"Idle period saved via API fallback")
        except Exception as fwd_err:
            print(f"Warning: Could not save idle period (MongoDB down, API fallback failed): {fwd_err}")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("collector_windows.py only runs on Windows.")

    tracker = WindowsTracker()
    tracker.run()
