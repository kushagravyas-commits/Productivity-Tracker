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

API_BASE_URL = os.getenv("TRACKER_API_BASE_URL", "http://127.0.0.1:8080")
CONFIG_PATH = APPDATA_PATH / "agent_config.json"

POLL_SECONDS = float(os.getenv("TRACKER_POLL_SECONDS", "2"))
MAX_SEGMENT_SECONDS = int(os.getenv("TRACKER_MAX_SEGMENT_SECONDS", "20"))
IDLE_THRESHOLD_SECONDS = int(os.getenv("TRACKER_IDLE_THRESHOLD_SECONDS", "300"))
TITLE_MAX_LENGTH = int(os.getenv("TRACKER_TITLE_MAX_LENGTH", "300"))
SOURCE_NAME = os.getenv("TRACKER_SOURCE_NAME", "windows_agent")
RULES_PATH = Path(os.getenv("TRACKER_RULES_PATH", APPDATA_PATH / "productivity_rules.json"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("TRACKER_REQUEST_TIMEOUT_SECONDS", "10"))
REGISTRATION_TOKEN = os.getenv("TRACKER_REGISTRATION_TOKEN")

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

        self.ensure_registered()
        # NOTE: add_to_startup() removed — Electron app handles startup registration
        self.install_extensions()

        self.rules = ProductivityRules.load(RULES_PATH)
        self.current_activity: OpenActivity | None = None
        self.idle_started_at: datetime | None = None
        self.running = True

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
        """Load saved config and re-register; prompt if still unassigned/rejected."""
        if CONFIG_PATH.exists():
            try:
                config = json.loads(CONFIG_PATH.read_text())
                if config.get("machine_guid") == self.machine_guid:
                    self.api_base_url = config.get("api_base_url", self.api_base_url)
                    print("Registration config loaded.")
                    # Always silently re-register so device stays linked in DB.
                    # If re-registration is not assigned (including rejected/unassigned),
                    # show onboarding dialog instead of silently continuing.
                    is_assigned = self.perform_registration()
                    if is_assigned:
                        return
                    self.show_registration_dialog()
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
                    # Save config to disk so next launch doesn't re-register
                    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                    CONFIG_PATH.write_text(json.dumps({
                        "machine_guid": self.machine_guid,
                        "api_base_url": self.api_base_url,
                        "role": data.get("role"),
                    }))
                    if data.get("assigned_user"):
                        print(f"Device assigned to {data['assigned_user']}")
                        return True
                    else:
                        print("Device registered. Waiting for admin assignment...")
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
        print(
            f"Starting Windows tracker. API={API_BASE_URL} poll={POLL_SECONDS}s "
            f"idle_threshold={IDLE_THRESHOLD_SECONDS}s max_segment={MAX_SEGMENT_SECONDS}s"
        )
        print(f"Rules file: {RULES_PATH}")

        while self.running:
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
            "started_at": started_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "ended_at": ended_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "app_name": snapshot.app_name,
            "window_title": snapshot.window_title,
            "url": snapshot.url,
            "category": snapshot.category,
            "productivity_label": snapshot.productivity_label,
            "notes": json.dumps({"process_name": snapshot.process_name, "classification_source": snapshot.category}),
            "source": SOURCE_NAME,
        }
        try:
            self.session.post(
                "http://127.0.0.1:8080/api/v1/events",
                json=payload,
                headers={"X-Machine-GUID": self.machine_guid},
                timeout=5,
            )
            print(f"Event: {snapshot.app_name} | {snapshot.productivity_label} | {started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Warning: Could not save event: {e}")

    def post_idle_period(self, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            return
        payload = {
            "started_at": started_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "ended_at": ended_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": "idle",
        }
        try:
            self.session.post(
                "http://127.0.0.1:8080/api/v1/idle",
                json=payload,
                headers={"X-Machine-GUID": self.machine_guid},
                timeout=5,
            )
            print(f"Idle: {started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Warning: Could not save idle period: {e}")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("collector_windows.py only runs on Windows.")

    tracker = WindowsTracker()
    tracker.run()
