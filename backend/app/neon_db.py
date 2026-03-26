"""Neon PostgreSQL — single database for all TrackFlow data.

Replaces MongoDB Atlas entirely. Core tables:
  events, idle_periods, users, devices,
  editor_context, browser_context, app_context,
  teams, team_members
"""
from __future__ import annotations

import os
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


def _clean_dsn(dsn: str) -> str:
    """Remove channel_binding param — asyncpg handles SSL natively."""
    dsn = re.sub(r'[?&]channel_binding=[^&]*', '', dsn)
    return dsn.rstrip('?&')


async def init_neon() -> None:
    global _pool
    dsn = os.getenv("NEONDB_URI")
    if not dsn:
        print("Warning: NEONDB_URI not set — data will not be stored.")
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
            CREATE TABLE IF NOT EXISTS users (
                id                 BIGSERIAL PRIMARY KEY,
                full_name          TEXT NOT NULL,
                email              TEXT UNIQUE NOT NULL,
                role               TEXT NOT NULL DEFAULT 'employee',
                registration_token TEXT UNIQUE NOT NULL,
                created_at         TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS devices (
                id           BIGSERIAL PRIMARY KEY,
                machine_guid TEXT UNIQUE NOT NULL,
                email        TEXT,
                os_type      TEXT,
                user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
                registered_at  TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                last_seen_at   TIMESTAMP WITHOUT TIME ZONE
            );
            CREATE INDEX IF NOT EXISTS idx_devices_email ON devices (email);

            CREATE TABLE IF NOT EXISTS events (
                id                 BIGSERIAL PRIMARY KEY,
                device_id          TEXT,
                started_at         TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                ended_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                app_name           TEXT NOT NULL,
                window_title       TEXT,
                url                TEXT,
                category           TEXT,
                productivity_label TEXT DEFAULT 'neutral',
                notes              TEXT,
                source             TEXT DEFAULT 'agent'
            );
            CREATE INDEX IF NOT EXISTS idx_events_device_started ON events (device_id, started_at);

            CREATE TABLE IF NOT EXISTS idle_periods (
                id         BIGSERIAL PRIMARY KEY,
                device_id  TEXT,
                started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                ended_at   TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                reason     TEXT DEFAULT 'idle'
            );
            CREATE INDEX IF NOT EXISTS idx_idle_device_started ON idle_periods (device_id, started_at);

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
            CREATE INDEX IF NOT EXISTS idx_ec_device_captured ON editor_context (device_id, captured_at);

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
            CREATE INDEX IF NOT EXISTS idx_bc_device_captured ON browser_context (device_id, captured_at);

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
            CREATE INDEX IF NOT EXISTS idx_ac_device_captured ON app_context (device_id, captured_at);

            CREATE TABLE IF NOT EXISTS teams (
                id          BIGSERIAL PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                created_at  TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                created_by  TEXT
            );

            CREATE TABLE IF NOT EXISTS team_members (
                team_id   BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                added_at  TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                PRIMARY KEY (team_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members (user_id);
        """)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

async def insert_event(r: dict) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events
              (device_id, started_at, ended_at, app_name, window_title,
               url, category, productivity_label, notes, source)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            r.get("device_id"),
            r["started_at"],
            r["ended_at"],
            r["app_name"],
            r.get("window_title"),
            r.get("url"),
            r.get("category"),
            r.get("productivity_label") or "neutral",
            r.get("notes"),
            r.get("source") or "agent",
        )


async def fetch_events(day: date, device_id: str | None) -> list[asyncpg.Record]:
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end   = datetime(day.year, day.month, day.day, 23, 59, 59)
    if device_id:
        return await _pool.fetch(
            "SELECT * FROM events WHERE device_id=$1 AND started_at>=$2 AND started_at<=$3 ORDER BY started_at",
            device_id, start, end,
        )
    return await _pool.fetch(
        "SELECT * FROM events WHERE started_at>=$1 AND started_at<=$2 ORDER BY started_at",
        start, end,
    )


async def fetch_events_list(day: date | None) -> list[asyncpg.Record]:
    """Fetch all events, optionally filtered to a day."""
    if day:
        start = datetime(day.year, day.month, day.day, 0, 0, 0)
        end   = datetime(day.year, day.month, day.day, 23, 59, 59)
        return await _pool.fetch(
            "SELECT * FROM events WHERE started_at>=$1 AND started_at<=$2 ORDER BY started_at LIMIT 5000",
            start, end,
        )
    return await _pool.fetch("SELECT * FROM events ORDER BY started_at LIMIT 5000")


# ---------------------------------------------------------------------------
# Idle periods
# ---------------------------------------------------------------------------

async def insert_idle_period(r: dict) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO idle_periods (device_id, started_at, ended_at, reason)
            VALUES ($1,$2,$3,$4)
            """,
            r.get("device_id"),
            r["started_at"],
            r["ended_at"],
            r.get("reason") or "idle",
        )


async def fetch_idle(day: date, device_id: str | None) -> list[asyncpg.Record]:
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end   = datetime(day.year, day.month, day.day, 23, 59, 59)
    if device_id:
        return await _pool.fetch(
            "SELECT * FROM idle_periods WHERE device_id=$1 AND started_at>=$2 AND started_at<=$3 ORDER BY started_at",
            device_id, start, end,
        )
    return await _pool.fetch(
        "SELECT * FROM idle_periods WHERE started_at>=$1 AND started_at<=$2 ORDER BY started_at",
        start, end,
    )


async def fetch_events_for_devices(day: date, device_ids: list[str]) -> list[asyncpg.Record]:
    """Events for a day across many device_ids (machine_guid)."""
    if not _pool or not device_ids:
        return []
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end = datetime(day.year, day.month, day.day, 23, 59, 59)
    return await _pool.fetch(
        """
        SELECT * FROM events
        WHERE device_id = ANY($1::text[])
          AND started_at >= $2 AND started_at <= $3
        ORDER BY started_at
        """,
        device_ids,
        start,
        end,
    )

async def fetch_latest_event_for_devices(day: date, device_ids: list[str]) -> asyncpg.Record | None:
    """Latest event within the given day for any of the device_ids."""
    if not _pool or not device_ids:
        return None
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end = datetime(day.year, day.month, day.day, 23, 59, 59)
    return await _pool.fetchrow(
        """
        SELECT *
        FROM events
        WHERE device_id = ANY($1::text[])
          AND started_at >= $2 AND started_at <= $3
        ORDER BY started_at DESC
        LIMIT 1
        """,
        device_ids,
        start,
        end,
    )


async def fetch_idle_for_devices(day: date, device_ids: list[str]) -> list[asyncpg.Record]:
    if not _pool or not device_ids:
        return []
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end = datetime(day.year, day.month, day.day, 23, 59, 59)
    return await _pool.fetch(
        """
        SELECT * FROM idle_periods
        WHERE device_id = ANY($1::text[])
          AND started_at >= $2 AND started_at <= $3
        ORDER BY started_at
        """,
        device_ids,
        start,
        end,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def find_user_by_email(email: str) -> asyncpg.Record | None:
    return await _pool.fetchrow("SELECT * FROM users WHERE email=$1", email)


async def find_user_by_id(user_id: int) -> asyncpg.Record | None:
    if not _pool:
        return None
    return await _pool.fetchrow("SELECT * FROM users WHERE id=$1", user_id)


async def find_user_by_token(token: str) -> asyncpg.Record | None:
    return await _pool.fetchrow("SELECT * FROM users WHERE registration_token=$1", token)


async def list_users() -> list[asyncpg.Record]:
    return await _pool.fetch("SELECT * FROM users ORDER BY created_at")


async def insert_user(full_name: str, email: str, role: str, token: str) -> asyncpg.Record:
    return await _pool.fetchrow(
        """
        INSERT INTO users (full_name, email, role, registration_token, created_at)
        VALUES ($1,$2,$3,$4,NOW()) RETURNING *
        """,
        full_name, email, role, token,
    )


async def upsert_user(email: str, full_name: str, role: str = "employee") -> asyncpg.Record:
    token = str(uuid.uuid4())[:8].upper()
    return await _pool.fetchrow(
        """
        INSERT INTO users (full_name, email, role, registration_token, created_at)
        VALUES ($1,$2,$3,$4,NOW())
        ON CONFLICT (email) DO UPDATE
          SET full_name=EXCLUDED.full_name, role=EXCLUDED.role
        RETURNING *
        """,
        full_name, email, role, token,
    )


async def update_user(_email: str, **fields: Any) -> int:
    """Update arbitrary fields. Returns matched row count (0 = not found)."""
    if not fields:
        return 0
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    vals = list(fields.values())
    result = await _pool.execute(f"UPDATE users SET {sets} WHERE email=$1", _email, *vals)
    return int(result.split()[-1])


async def delete_user(email: str) -> int:
    result = await _pool.execute("DELETE FROM users WHERE email=$1", email)
    return int(result.split()[-1])


async def user_id_to_team_ids_map() -> dict[int, list[int]]:
    """Map user_id -> list of team_ids (for admin list users)."""
    if not _pool:
        return {}
    rows = await _pool.fetch("SELECT user_id, team_id FROM team_members")
    m: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        m[int(r["user_id"])].append(int(r["team_id"]))
    return dict(m)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


async def list_teams() -> list[asyncpg.Record]:
    if not _pool:
        return []
    return await _pool.fetch("SELECT * FROM teams ORDER BY LOWER(name)")


async def get_team(team_id: int) -> asyncpg.Record | None:
    if not _pool:
        return None
    return await _pool.fetchrow("SELECT * FROM teams WHERE id=$1", team_id)


async def create_team(name: str, created_by: str | None) -> asyncpg.Record:
    return await _pool.fetchrow(
        "INSERT INTO teams (name, created_by) VALUES ($1, $2) RETURNING *",
        name.strip(),
        created_by,
    )


async def update_team_name(team_id: int, name: str) -> int:
    result = await _pool.execute(
        "UPDATE teams SET name=$2 WHERE id=$1",
        team_id,
        name.strip(),
    )
    return int(result.split()[-1])


async def delete_team(team_id: int) -> int:
    result = await _pool.execute("DELETE FROM teams WHERE id=$1", team_id)
    return int(result.split()[-1])


async def get_team_user_ids(team_id: int) -> list[int]:
    if not _pool:
        return []
    rows = await _pool.fetch(
        "SELECT user_id FROM team_members WHERE team_id=$1 ORDER BY user_id",
        team_id,
    )
    return [int(r["user_id"]) for r in rows]


async def get_team_members_with_users(team_id: int) -> list[asyncpg.Record]:
    if not _pool:
        return []
    return await _pool.fetch(
        """
        SELECT u.id, u.full_name, u.email, u.role, u.registration_token, u.created_at, tm.added_at
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = $1
        ORDER BY u.full_name
        """,
        team_id,
    )


async def set_team_members(team_id: int, user_ids: list[int]) -> None:
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM team_members WHERE team_id=$1", team_id)
            for uid in user_ids:
                await conn.execute(
                    """
                    INSERT INTO team_members (team_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (team_id, user_id) DO NOTHING
                    """,
                    team_id,
                    uid,
                )


async def get_machine_guids_for_user_id(user_id: int) -> list[str]:
    if not _pool:
        return []
    rows = await _pool.fetch(
        "SELECT machine_guid FROM devices WHERE user_id=$1",
        user_id,
    )
    return [r["machine_guid"] for r in rows if r.get("machine_guid")]


async def get_machine_guids_for_user_ids(user_ids: list[int]) -> list[str]:
    if not _pool or not user_ids:
        return []
    rows = await _pool.fetch(
        "SELECT DISTINCT machine_guid FROM devices WHERE user_id = ANY($1::bigint[])",
        user_ids,
    )
    return [r["machine_guid"] for r in rows if r.get("machine_guid")]


async def get_primary_device_for_user(user_id: int) -> asyncpg.Record | None:
    if not _pool:
        return None
    return await _pool.fetchrow(
        """
        SELECT * FROM devices
        WHERE user_id=$1
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT 1
        """,
        user_id,
    )


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

async def find_device_by_guid(guid: str) -> asyncpg.Record | None:
    return await _pool.fetchrow("SELECT * FROM devices WHERE machine_guid=$1", guid)


async def list_devices() -> list[asyncpg.Record]:
    return await _pool.fetch("SELECT * FROM devices ORDER BY registered_at")


async def upsert_device(machine_guid: str, email: str | None, os_type: str | None) -> asyncpg.Record:
    return await _pool.fetchrow(
        """
        INSERT INTO devices (machine_guid, email, os_type, registered_at, last_seen_at)
        VALUES ($1,$2,$3,NOW(),NOW())
        ON CONFLICT (machine_guid) DO UPDATE
          SET email=COALESCE(EXCLUDED.email, devices.email),
              os_type=COALESCE(EXCLUDED.os_type, devices.os_type),
              last_seen_at=NOW()
        RETURNING *
        """,
        machine_guid, email, os_type,
    )


async def link_device_to_user(machine_guid: str, user_id: int, email: str) -> None:
    await _pool.execute(
        "UPDATE devices SET user_id=$2, email=$3, last_seen_at=NOW() WHERE machine_guid=$1",
        machine_guid, user_id, email,
    )


async def update_device_email(old_email: str, new_email: str) -> None:
    await _pool.execute(
        "UPDATE devices SET email=$2 WHERE email=$1",
        old_email, new_email,
    )


# ---------------------------------------------------------------------------
# Context tables (editor, browser, app)
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


async def query_context(
    table: str,
    day: date,
    device_id: str | None,
    since_dt: datetime | None,
    limit: int,
) -> list[asyncpg.Record]:
    """Fetch context rows for a day, filtered by device_id when provided."""
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end   = datetime(day.year, day.month, day.day, 23, 59, 59)
    if device_id:
        if since_dt is not None:
            return await _pool.fetch(
                f"SELECT * FROM {table} WHERE device_id=$1 AND captured_at>$2 AND captured_at<=$3 ORDER BY captured_at LIMIT $4",
                device_id, since_dt, end, limit,
            )
        return await _pool.fetch(
            f"SELECT * FROM {table} WHERE device_id=$1 AND captured_at>=$2 AND captured_at<=$3 ORDER BY captured_at LIMIT $4",
            device_id, start, end, limit,
        )
    # No device_id — return all (admin view)
    if since_dt is not None:
        return await _pool.fetch(
            f"SELECT * FROM {table} WHERE captured_at>$1 AND captured_at<=$2 ORDER BY captured_at LIMIT $3",
            since_dt, end, limit,
        )
    return await _pool.fetch(
        f"SELECT * FROM {table} WHERE captured_at>=$1 AND captured_at<=$2 ORDER BY captured_at LIMIT $3",
        start, end, limit,
    )
