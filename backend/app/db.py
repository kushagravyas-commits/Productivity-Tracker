from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Production paths: Store in %APPDATA%\TrackFlow
APPDATA_PATH = Path(os.getenv("APPDATA", Path.home() / "AppData/Roaming")) / "TrackFlow"
APPDATA_PATH.mkdir(parents=True, exist_ok=True)

LOCAL_DB_PATH = Path("tracker.db").resolve()
DEFAULT_DB_PATH = APPDATA_PATH / "tracker.db"

# Check if local exists first, otherwise use APPDATA
if "DATABASE_PATH" in os.environ:
    DATABASE_PATH = Path(os.environ["DATABASE_PATH"]).resolve()
elif LOCAL_DB_PATH.exists():
    DATABASE_PATH = LOCAL_DB_PATH
else:
    DATABASE_PATH = DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency in multi-user setup
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Core Tables for Multi-User Support
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            registration_token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_guid TEXT UNIQUE NOT NULL,
            os_type TEXT,
            user_id INTEGER,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    # Activity Tables (Updated with device_id)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            app_name TEXT NOT NULL,
            window_title TEXT,
            url TEXT,
            category TEXT,
            productivity_label TEXT,
            notes TEXT,
            source TEXT DEFAULT 'agent',
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS idle_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            reason TEXT DEFAULT 'idle',
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS editor_context (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id       INTEGER,
            captured_at     TEXT NOT NULL,
            editor_app      TEXT NOT NULL DEFAULT 'VS Code',
            workspace       TEXT,
            active_file     TEXT,
            active_file_path TEXT,
            language        TEXT,
            open_files      TEXT,
            terminal_count  INTEGER DEFAULT 0,
            git_branch      TEXT,
            debugger_active INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS browser_context (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           INTEGER,
            captured_at         TEXT NOT NULL,
            browser_app         TEXT NOT NULL,
            active_tab_url      TEXT,
            active_tab_title    TEXT,
            active_tab_domain   TEXT,
            tab_count           INTEGER DEFAULT 0,
            open_domains        TEXT,   -- JSON array
            youtube_video_title TEXT,
            youtube_channel     TEXT,
            youtube_is_playing  INTEGER DEFAULT 0,
            youtube_progress_pct INTEGER,
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_context (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           INTEGER,
            captured_at         TEXT NOT NULL,
            app_name            TEXT NOT NULL,
            active_file_name    TEXT,
            active_file_path    TEXT,
            active_sequence     TEXT,
            notes               TEXT,
            FOREIGN KEY (device_id) REFERENCES devices (id)
        )
        """
    )

    # Migration: Add device_id column to existing tables if it doesn't exist
    tables_to_update = ["events", "idle_periods", "editor_context", "browser_context", "app_context"]
    for table in tables_to_update:
        cur.execute(f"PRAGMA table_info({table})")
        columns = [column[1] for column in cur.fetchall()]
        if "device_id" not in columns:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN device_id INTEGER")

    conn.commit()
    conn.close()
