from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./tracker.db")).resolve()


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            app_name TEXT NOT NULL,
            window_title TEXT,
            url TEXT,
            category TEXT,
            productivity_label TEXT,
            notes TEXT,
            source TEXT DEFAULT 'agent'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS idle_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            reason TEXT DEFAULT 'idle'
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
            captured_at     TEXT NOT NULL,
            editor_app      TEXT NOT NULL DEFAULT 'VS Code',
            workspace       TEXT,
            active_file     TEXT,
            active_file_path TEXT,
            language        TEXT,
            open_files      TEXT,
            terminal_count  INTEGER DEFAULT 0,
            git_branch      TEXT,
            debugger_active INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS browser_context (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
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
            youtube_progress_pct INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_context (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at         TEXT NOT NULL,
            app_name            TEXT NOT NULL,
            active_file_name    TEXT,
            active_file_path    TEXT,
            active_sequence     TEXT,
            notes               TEXT
        )
        """
    )
    conn.commit()

    conn.close()
