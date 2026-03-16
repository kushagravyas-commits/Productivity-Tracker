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

import psutil
import requests

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32

API_BASE_URL = os.getenv("TRACKER_API_BASE_URL", "http://127.0.0.1:8000")
EVENTS_URL = f"{API_BASE_URL.rstrip('/')}/api/v1/events"
IDLE_URL = f"{API_BASE_URL.rstrip('/')}/api/v1/idle"
POLL_SECONDS = float(os.getenv("TRACKER_POLL_SECONDS", "2"))
MAX_SEGMENT_SECONDS = int(os.getenv("TRACKER_MAX_SEGMENT_SECONDS", "20"))
IDLE_THRESHOLD_SECONDS = int(os.getenv("TRACKER_IDLE_THRESHOLD_SECONDS", "300"))
TITLE_MAX_LENGTH = int(os.getenv("TRACKER_TITLE_MAX_LENGTH", "300"))
SOURCE_NAME = os.getenv("TRACKER_SOURCE_NAME", "windows_agent")
RULES_PATH = Path(os.getenv("TRACKER_RULES_PATH", Path(__file__).with_name("productivity_rules.json")))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("TRACKER_REQUEST_TIMEOUT_SECONDS", "10"))

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
        self.session = requests.Session()
        self.rules = ProductivityRules.load(RULES_PATH)
        self.current_activity: OpenActivity | None = None
        self.idle_started_at: datetime | None = None
        self.running = True

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
        hwnd = USER32.GetForegroundWindow()
        if not hwnd:
            return None

        title = self.get_window_title(hwnd)
        if not title:
            return None

        pid = ctypes.c_ulong()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = self.get_process_name(pid.value)
        app_name = PROCESS_ALIASES.get(process_name.lower(), Path(process_name).stem or process_name or "Unknown")
        app_name = app_name if app_name else "Unknown"

        productivity_label, category = self.rules.classify(process_name, title)

        return WindowSnapshot(
            app_name=app_name,
            process_name=process_name.lower(),
            window_title=title[:TITLE_MAX_LENGTH],
            url=None,
            category=category,
            productivity_label=productivity_label,
        )

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        length = USER32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        USER32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value.strip()

    @staticmethod
    def get_process_name(pid: int) -> str:
        if pid <= 0:
            return "unknown.exe"
        try:
            return psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "unknown.exe"

    @staticmethod
    def get_idle_seconds() -> float:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not USER32.GetLastInputInfo(ctypes.byref(info)):
            raise ctypes.WinError()
        millis_since_last_input = KERNEL32.GetTickCount() - info.dwTime
        return max(millis_since_last_input / 1000.0, 0.0)

    def post_event(self, snapshot: WindowSnapshot, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            return
        payload = {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
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
        response = self.session.post(EVENTS_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        print(
            f"Event posted: {snapshot.app_name} | {snapshot.productivity_label} | "
            f"{started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}"
        )

    def post_idle_period(self, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            return
        payload = {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "reason": "idle",
        }
        response = self.session.post(IDLE_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        print(f"Idle period posted: {started_at.strftime('%H:%M:%S')} -> {ended_at.strftime('%H:%M:%S')}")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("collector_windows.py only runs on Windows.")

    tracker = WindowsTracker()
    tracker.run()
