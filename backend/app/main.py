from __future__ import annotations

import os
from datetime import date, datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.db import get_connection, init_db
from app.schemas import (
    DashboardResponse,
    EditorContextIn,
    EditorContextItem,
    BrowserContextIn,
    BrowserContextItem,
    EventIn,
    HealthResponse,
    HistoryResponse,
    IdlePeriodIn,
    MessageResponse,
    SettingsResponse,
    SettingUpdate,
)
from app.services.analytics import (
    build_kpis,
    build_productivity_breakdown,
    build_sessions,
    build_timeline,
    build_top_app_items,
    clamp_duration_seconds,
    rows_to_dicts,
    split_by_day,
    summarize_day,
)

APP_NAME = os.getenv("APP_NAME", "TrackFlow")
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]

app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name=APP_NAME)


@app.post("/api/v1/events", response_model=MessageResponse)
def ingest_event(event: EventIn) -> MessageResponse:
    if event.ended_at <= event.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO events (
            started_at, ended_at, app_name, window_title, url, category,
            productivity_label, notes, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.started_at.isoformat(),
            event.ended_at.isoformat(),
            event.app_name,
            event.window_title,
            event.url,
            event.category,
            event.productivity_label,
            event.notes,
            event.source,
        ),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="event ingested")


@app.post("/api/v1/idle", response_model=MessageResponse)
def ingest_idle_period(period: IdlePeriodIn) -> MessageResponse:
    if period.ended_at <= period.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO idle_periods (started_at, ended_at, reason) VALUES (?, ?, ?)",
        (period.started_at.isoformat(), period.ended_at.isoformat(), period.reason),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="idle period ingested")





@app.get("/api/v1/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return SettingsResponse(settings={row["key"]: row["value"] for row in rows})


@app.put("/api/v1/settings", response_model=MessageResponse)
def update_setting(payload: SettingUpdate) -> MessageResponse:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (payload.key, payload.value),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="setting updated", detail={payload.key: payload.value})


@app.get("/api/v1/dashboard/today", response_model=DashboardResponse)
def dashboard_today() -> DashboardResponse:
    return dashboard(date.today())


@app.get("/api/v1/dashboard/{day}", response_model=DashboardResponse)
def dashboard(day: date) -> DashboardResponse:
    conn = get_connection()
    cur = conn.cursor()
    rows = rows_to_dicts(cur.execute("SELECT * FROM events ORDER BY started_at").fetchall())
    idle_rows = rows_to_dicts(cur.execute("SELECT * FROM idle_periods ORDER BY started_at").fetchall())
    conn.close()

    day_events = split_by_day(rows, day)
    day_idle = split_by_day(idle_rows, day)
    
    idle_seconds = sum(
        clamp_duration_seconds(row["started_at"], row["ended_at"])
        for row in day_idle
    )

    return DashboardResponse(
        day=day,
        kpis=build_kpis(day_events, idle_seconds),
        top_apps=build_top_app_items(day_events),
        timeline=build_timeline(day_events, day_idle),
        productivity_breakdown=build_productivity_breakdown(day_events, idle_seconds),
        summary=summarize_day(day_events, idle_seconds),
    )


@app.get("/api/v1/history/{day}", response_model=HistoryResponse)
def history(day: date) -> HistoryResponse:
    conn = get_connection()
    cur = conn.cursor()
    rows = rows_to_dicts(cur.execute("SELECT * FROM events ORDER BY started_at").fetchall())
    idle_rows = rows_to_dicts(cur.execute("SELECT * FROM idle_periods ORDER BY started_at").fetchall())
    conn.close()

    day_events = split_by_day(rows, day)
    idle_seconds = sum(
        clamp_duration_seconds(row["started_at"], row["ended_at"])
        for row in idle_rows
        if datetime.fromisoformat(row["started_at"]).date() == day
    )

    return HistoryResponse(
        day=day,
        sessions=build_sessions(day_events),
        day_summary=summarize_day(day_events, idle_seconds),
    )


@app.get("/api/v1/events", response_model=list[EventIn])
def list_events(
    day: Annotated[date | None, Query(description="Optional date filter in YYYY-MM-DD")] = None,
) -> list[EventIn]:
    conn = get_connection()
    cur = conn.cursor()
    rows = rows_to_dicts(cur.execute("SELECT * FROM events ORDER BY started_at").fetchall())
    conn.close()

    if day:
        rows = split_by_day(rows, day)
    return [
        EventIn(
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]),
            app_name=row["app_name"],
            window_title=row.get("window_title"),
            url=row.get("url"),
            category=row.get("category"),
            productivity_label=row.get("productivity_label") or "neutral",
            notes=row.get("notes"),
            source=row.get("source") or "agent",
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Editor context endpoints  (data from VS Code / Antigravity extension)
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/editor", response_model=MessageResponse, tags=["editor"])
def post_editor_context(payload: EditorContextIn) -> MessageResponse:
    """Receive an editor context snapshot from the VS Code / Antigravity extension."""
    import json as _json

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO editor_context
            (captured_at, editor_app, workspace, active_file, active_file_path,
             language, open_files, terminal_count, git_branch, debugger_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.captured_at.isoformat(),
            payload.editor_app,
            payload.workspace,
            payload.active_file,
            payload.active_file_path,
            payload.language,
            _json.dumps(payload.open_files),
            payload.terminal_count,
            payload.git_branch,
            int(payload.debugger_active),
        ),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="ok")


@app.get("/api/v1/context/editor/{day}", response_model=list[EditorContextItem], tags=["editor"])
def get_editor_context(day: str) -> list[EditorContextItem]:
    """Return all editor context snapshots for a given day (YYYY-MM-DD)."""
    import json as _json

    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    day_start = f"{target}T00:00:00"
    day_end   = f"{target}T23:59:59"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, captured_at, editor_app, workspace, active_file,
               active_file_path, language, open_files, terminal_count,
               git_branch, debugger_active
        FROM   editor_context
        WHERE  captured_at >= ? AND captured_at <= ?
        ORDER  BY captured_at ASC
        """,
        (day_start, day_end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return [
        EditorContextItem(
            id=r["id"],
            captured_at=datetime.fromisoformat(r["captured_at"]),
            editor_app=r["editor_app"],
            workspace=r["workspace"],
            active_file=r["active_file"],
            active_file_path=r["active_file_path"],
            language=r["language"],
            open_files=_json.loads(r["open_files"]) if r["open_files"] else [],
            terminal_count=r["terminal_count"] or 0,
            git_branch=r["git_branch"],
            debugger_active=bool(r["debugger_active"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Browser context endpoints  (data from Chrome / Brave extension)
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/browser", response_model=MessageResponse, tags=["browser"])
def post_browser_context(payload: BrowserContextIn) -> MessageResponse:
    """Receive a browser context snapshot from the Chrome / Brave extension."""
    import json as _json

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO browser_context
            (captured_at, browser_app, active_tab_url, active_tab_title,
             active_tab_domain, tab_count, open_domains, youtube_video_title,
             youtube_channel, youtube_is_playing, youtube_progress_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.captured_at.isoformat(),
            payload.browser_app,
            payload.active_tab_url,
            payload.active_tab_title,
            payload.active_tab_domain,
            payload.tab_count,
            _json.dumps(payload.open_domains),
            payload.youtube_video_title,
            payload.youtube_channel,
            int(payload.youtube_is_playing) if payload.youtube_is_playing is not None else None,
            payload.youtube_progress_pct,
        ),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="ok")


@app.get("/api/v1/context/browser/{day}", response_model=list[BrowserContextItem], tags=["browser"])
def get_browser_context(day: str) -> list[BrowserContextItem]:
    """Return all browser context snapshots for a given day (YYYY-MM-DD)."""
    import json as _json

    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    day_start = f"{target}T00:00:00"
    day_end   = f"{target}T23:59:59"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, captured_at, browser_app, active_tab_url, active_tab_title,
               active_tab_domain, tab_count, open_domains, youtube_video_title,
               youtube_channel, youtube_is_playing, youtube_progress_pct
        FROM   browser_context
        WHERE  captured_at >= ? AND captured_at <= ?
        ORDER  BY captured_at ASC
        """,
        (day_start, day_end),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    from app.services.classifier import classifier
    return [
        BrowserContextItem(
            id=r["id"],
            captured_at=datetime.fromisoformat(r["captured_at"]),
            browser_app=r["browser_app"],
            active_tab_url=r["active_tab_url"],
            active_tab_title=r["active_tab_title"],
            active_tab_domain=r["active_tab_domain"],
            tab_count=r["tab_count"] or 0,
            open_domains=_json.loads(r["open_domains"]) if r["open_domains"] else [],
            youtube_video_title=r["youtube_video_title"],
            youtube_channel=r["youtube_channel"],
            youtube_is_playing=bool(r["youtube_is_playing"]) if r["youtube_is_playing"] is not None else None,
            youtube_progress_pct=r["youtube_progress_pct"],
            productivity_label=classifier.classify(r["active_tab_title"], r["active_tab_domain"])
        )
        for r in rows
    ]

@app.post("/api/v1/context/app", response_model=MessageResponse, tags=["app"])
def post_app_context(payload: AppContextIn) -> MessageResponse:
    """Receive a generic application context snapshot (Adobe, DaVinci, etc.)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app_context
            (captured_at, app_name, active_file_name, active_file_path, active_sequence, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.captured_at.isoformat(),
            payload.app_name,
            payload.active_file_name,
            payload.active_file_path,
            payload.active_sequence,
            payload.notes,
        ),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="ok")
