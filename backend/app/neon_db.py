"""Neon PostgreSQL connection and helpers for Deep Activity context tables.

editor_context, browser_context, and app_context are stored here instead of
MongoDB Atlas to avoid the 10-15s read timeouts on the free Atlas tier.
Everything else (events, idle_periods, dashboard, devices) stays on MongoDB.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

import asyncpg

_pool: asyncpg.Pool | None = None


def _clean_dsn(dsn: str) -> str:
    """Remove channel_binding param — asyncpg handles SSL natively, not via DSN."""
    dsn = re.sub(r'[?&]channel_binding=[^&]*', '', dsn)
    return dsn.rstrip('?&')


async def init_neon() -> None:
    global _pool
    dsn = os.getenv("NEONDB_URI")
    if not dsn:
        print("Warning: NEONDB_URI not set — context data will not be stored in Neon.")
        return
    _pool = await asyncpg.create_pool(_clean_dsn(dsn), ssl='require', min_size=1, max_size=5)
    await _create_tables()
    print("Neon PostgreSQL connected.")


async def close_neon() -> None:
    if _pool:
        await _pool.close()


def is_ready() -> bool:
    return _pool is not None


async def _create_tables() -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS editor_context (
                id               BIGSERIAL PRIMARY KEY,
                device_id        TEXT,
                captured_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                editor_app       TEXT NOT NULL DEFAULT 'VS Code',
                workspace        TEXT,
                active_file      TEXT,
                active_file_path TEXT,
                language         TEXT,
                open_files       TEXT[] DEFAULT '{}',
                terminal_count   INT DEFAULT 0,
                git_branch       TEXT,
                debugger_active  BOOLEAN DEFAULT FALSE
            );
            CREATE INDEX IF NOT EXISTS idx_ec_device_captured
                ON editor_context (device_id, captured_at);

            CREATE TABLE IF NOT EXISTS browser_context (
                id                   BIGSERIAL PRIMARY KEY,
                device_id            TEXT,
                captured_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                browser_app          TEXT NOT NULL,
                active_tab_url       TEXT,
                active_tab_title     TEXT,
                active_tab_domain    TEXT,
                tab_count            INT DEFAULT 0,
                open_domains         TEXT[] DEFAULT '{}',
                youtube_video_title  TEXT,
                youtube_channel      TEXT,
                youtube_is_playing   BOOLEAN,
                youtube_progress_pct INT,
                productivity_label   TEXT DEFAULT 'neutral'
            );
            CREATE INDEX IF NOT EXISTS idx_bc_device_captured
                ON browser_context (device_id, captured_at);

            CREATE TABLE IF NOT EXISTS app_context (
                id               BIGSERIAL PRIMARY KEY,
                device_id        TEXT,
                captured_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                app_name         TEXT NOT NULL,
                active_file_name TEXT,
                active_file_path TEXT,
                active_sequence  TEXT,
                notes            TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ac_device_captured
                ON app_context (device_id, captured_at);
        """)


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

async def insert_editor_context(r: dict) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO editor_context
              (device_id, captured_at, editor_app, workspace, active_file,
               active_file_path, language, open_files, terminal_count,
               git_branch, debugger_active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            r.get("device_id"),
            r["captured_at"],
            r.get("editor_app") or "VS Code",
            r.get("workspace"),
            r.get("active_file"),
            r.get("active_file_path"),
            r.get("language"),
            r.get("open_files") or [],
            r.get("terminal_count") or 0,
            r.get("git_branch"),
            bool(r.get("debugger_active")),
        )


async def insert_browser_context(r: dict) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO browser_context
              (device_id, captured_at, browser_app, active_tab_url,
               active_tab_title, active_tab_domain, tab_count, open_domains,
               youtube_video_title, youtube_channel, youtube_is_playing,
               youtube_progress_pct, productivity_label)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            """,
            r.get("device_id"),
            r["captured_at"],
            r.get("browser_app") or "Unknown",
            r.get("active_tab_url"),
            r.get("active_tab_title"),
            r.get("active_tab_domain"),
            r.get("tab_count") or 0,
            r.get("open_domains") or [],
            r.get("youtube_video_title"),
            r.get("youtube_channel"),
            r.get("youtube_is_playing"),
            r.get("youtube_progress_pct"),
            r.get("productivity_label") or "neutral",
        )


async def insert_app_context(r: dict) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO app_context
              (device_id, captured_at, app_name, active_file_name,
               active_file_path, active_sequence, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            r.get("device_id"),
            r["captured_at"],
            r.get("app_name") or "Unknown",
            r.get("active_file_name"),
            r.get("active_file_path"),
            r.get("active_sequence"),
            r.get("notes"),
        )


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------

async def query_context(
    table: str,
    day: date,
    device_id: str | None,
    since_dt: datetime | None,
    limit: int,
) -> list[asyncpg.Record]:
    """Fetch rows for a given day from a context table.

    device_id is intentionally ignored — browser/editor extensions each generate
    their own UUID which doesn't match the Windows machine GUID the frontend uses.
    Context data is single-machine so no device filtering is needed.
    """
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end   = datetime(day.year, day.month, day.day, 23, 59, 59)
    after = since_dt if since_dt is not None else start

    return await _pool.fetch(
        f"SELECT * FROM {table}"
        " WHERE captured_at>$1 AND captured_at<=$2"
        " ORDER BY captured_at LIMIT $3",
        after, end, limit,
    )
