from __future__ import annotations

import os
import sys
import uuid as uuid_pkg
from datetime import date, datetime
from typing import Annotated

# Fix stdout/stderr for PyInstaller --noconsole mode (Windows sets them to None)
if getattr(sys, "frozen", False) and sys.stdout is None:
    from pathlib import Path as _P
    _log_path = _P(os.getenv("APPDATA", _P.home() / "AppData/Roaming")) / "TrackFlow" / "server.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_file
    sys.stderr = _log_file

from dotenv import load_dotenv

# When running as a PyInstaller EXE, .env is extracted to sys._MEIPASS
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_base, ".env"))

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from contextlib import asynccontextmanager

from app.db import get_connection, init_db
from app import neon_db
from app.schemas import (
    DashboardResponse,
    EditorContextIn,
    EditorContextItem,
    BrowserContextIn,
    BrowserContextItem,
    AppContextIn,
    AppContextItem,
    EventIn,
    HealthResponse,
    HistoryResponse,
    IdlePeriodIn,
    MessageResponse,
    SettingsResponse,
    SettingUpdate,
    UserItem,
    UserIn,
    UserUpdateIn,
    DeviceRegisterIn,
    DeviceItem,
    DeviceAssignIn,
    UserRoleUpdateIn,
    RegisterResponse,
)
from app.services.analytics import (
    build_kpis,
    build_productivity_breakdown,
    build_sessions,
    build_timeline,
    build_top_app_items,
    clamp_duration_seconds,
    summarize_day,
)

ALLOWED_ADMIN_EMAILS = [
    "kushagra.vyas@varaheanalytics.com",
    "raj.sharma@varaheanalytics.com",
    "nitin.by@varaheanalytics.com"
]

APP_NAME = os.getenv("APP_NAME", "TrackFlow")

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache
# ---------------------------------------------------------------------------
from time import time as _now

_cache: dict[str, tuple[float, object]] = {}

def cache_get(key: str, ttl: float) -> object | None:
    entry = _cache.get(key)
    if entry and _now() - entry[0] < ttl:
        return entry[1]
    return None

def cache_set(key: str, value: object) -> None:
    _cache[key] = (_now(), value)

def naive_day_range(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, datetime.min.time()), datetime.combine(day, datetime.max.time())

def parse_local_time(val) -> datetime:
    if isinstance(val, str):
        val = val.replace('Z', '+00:00') if 'Z' in val else val
        val = datetime.fromisoformat(val)
    if not isinstance(val, datetime):
        return val
    if val.tzinfo is not None:
        val = val.astimezone()
        val = val.replace(tzinfo=None)
    return val

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()              # SQLite for settings/admin status
    await neon_db.init_neon()
    yield
    await neon_db.close_neon()


app = FastAPI(title="TrackFlow API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Serve frontend static files
if getattr(sys, 'frozen', False):
    static_dir = Path(sys._MEIPASS) / "static"
else:
    static_dir = Path(__file__).parent.parent / "static"

if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app_name": APP_NAME, "neon_connected": neon_db.is_ready()}


async def get_device_id(machine_guid: str | None = Header(None, alias="X-Machine-GUID")) -> str | None:
    return machine_guid


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.post("/api/v1/admin/users", response_model=UserItem, tags=["admin"])
async def create_user(user: UserIn) -> UserItem:
    existing = await neon_db.find_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=409, detail=f"User with email {user.email} already exists")
    token = str(uuid_pkg.uuid4())[:8].upper()
    try:
        row = await neon_db.insert_user(user.full_name, user.email, user.role, token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create user: {e}")
    return UserItem(
        id=row["id"],
        full_name=row["full_name"],
        email=row["email"],
        role=row["role"],
        registration_token=row["registration_token"],
        created_at=row["created_at"],
    )


@app.get("/api/v1/admin/users", response_model=list[UserItem], tags=["admin"])
async def list_users() -> list[UserItem]:
    rows = await neon_db.list_users()
    return [
        UserItem(
            id=r["id"],
            full_name=r["full_name"],
            email=r["email"],
            role=r.get("role") or "employee",
            registration_token=r["registration_token"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@app.delete("/api/v1/admin/users/{email}", response_model=MessageResponse, tags=["admin"])
async def delete_user(email: str) -> MessageResponse:
    count = await neon_db.delete_user(email)
    if count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} deleted successfully")


@app.put("/api/v1/admin/users/{email}/role", response_model=MessageResponse, tags=["admin"])
async def update_user_role(email: str, payload: UserRoleUpdateIn) -> MessageResponse:
    count = await neon_db.update_user(email, role=payload.role)
    if count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} role updated to {payload.role}")


@app.put("/api/v1/admin/users/{email}", response_model=MessageResponse, tags=["admin"])
async def update_user(email: str, payload: UserUpdateIn) -> MessageResponse:
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        return MessageResponse(message="No changes provided")
    new_email = update_data.pop("email", None)
    if new_email and new_email != email:
        await neon_db.update_device_email(email, new_email)
        update_data["email"] = new_email
    count = await neon_db.update_user(email, **update_data)
    if count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} updated successfully")


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

@app.get("/api/v1/admin/devices", response_model=list[DeviceItem], tags=["admin"])
async def list_devices() -> list[DeviceItem]:
    rows = await neon_db.list_devices()
    return [
        DeviceItem(
            id=r["id"],
            machine_guid=r["machine_guid"],
            os_type=r.get("os_type"),
            user_id=r.get("user_id"),
            email=r.get("email"),
            registered_at=r["registered_at"],
            last_seen_at=r.get("last_seen_at"),
        )
        for r in rows
    ]


@app.post("/api/v1/admin/devices/{machine_guid}/assign", response_model=MessageResponse, tags=["admin"])
async def assign_device(machine_guid: str, payload: DeviceAssignIn) -> MessageResponse:
    user = await neon_db.upsert_user(payload.email, payload.full_name, payload.role)
    device = await neon_db.upsert_device(machine_guid, payload.email, None)
    await neon_db.link_device_to_user(machine_guid, user["id"], payload.email)
    return MessageResponse(message=f"Device {machine_guid[:8]} assigned to {payload.email}")


@app.get("/api/v1/machine-guid", tags=["registration"])
def get_backend_machine_guid():
    """Return the unique hardware ID of the machine where this server is running."""
    try:
        import sys
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return {"machine_guid": guid}
        elif sys.platform == "darwin":
            import subprocess
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); printf(\"%s\", line[4]); }'"
            out = subprocess.check_output(cmd, shell=True).decode().strip()
            if out: return {"machine_guid": out}
    except Exception as e:
        print(f"Error getting machine guid: {e}")
    return {"machine_guid": None}

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@app.post("/api/v1/register", response_model=RegisterResponse, tags=["registration"])
async def register_device(reg: DeviceRegisterIn) -> RegisterResponse:
    resp = RegisterResponse(message="Device reported.")
    # mongodb_uri is no longer used — return None for backward compatibility
    resp.mongodb_uri = None
    resp.mongodb_db = None

    if reg.registration_token:
        user = await neon_db.find_user_by_token(reg.registration_token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid registration token")
        device = await neon_db.upsert_device(reg.machine_guid, user["email"], reg.os_type)
        await neon_db.link_device_to_user(reg.machine_guid, user["id"], user["email"])
        resp.assigned_user = user["full_name"]
        resp.role = user.get("role", "employee")
        resp.message = "Device registered and assigned."

    elif reg.full_name and reg.email:
        # First user ever - auto-assign admin role
        existing_users = await neon_db.list_users()
        is_first = not existing_users
        role = "admin" if is_first else "employee"
        user = await neon_db.upsert_user(reg.email, reg.full_name, role)
        device = await neon_db.upsert_device(reg.machine_guid, reg.email, reg.os_type)
        await neon_db.link_device_to_user(reg.machine_guid, user["id"], reg.email)
        if is_first:
            # Auto-setup admin panel access in SQLite for the first user
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("admin_email", reg.email.lower().strip()),
            )
            conn.commit()
            conn.close()
        resp.assigned_user = user["full_name"]
        resp.role = user.get("role", role)
        resp.message = "Device registered and assigned."

    else:
        await neon_db.upsert_device(reg.machine_guid, None, reg.os_type)
        device = await neon_db.find_device_by_guid(reg.machine_guid)
        if device and device.get("email"):
            user = await neon_db.find_user_by_email(device["email"])
            if user:
                resp.assigned_user = user["full_name"]
                resp.role = user.get("role", "employee")
                resp.message = "Device registered and assigned."

    return resp


@app.get("/api/v1/machine-guid", tags=["registration"])
async def get_machine_guid() -> dict:
    """Read this machine's Windows Machine GUID from the registry."""
    import subprocess
    try:
        out = subprocess.check_output(
            ['reg', 'query', r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography', '/v', 'MachineGuid'],
            encoding='utf-8', stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            if 'MachineGuid' in line:
                parts = line.strip().split()
                return {"machine_guid": parts[-1]}
    except Exception:
        pass
    return {"machine_guid": None}


@app.get("/api/v1/device-role/{machine_guid}", tags=["registration"])
async def get_device_role(machine_guid: str) -> dict:
    """Return the role for the user linked to this device."""
    device = await neon_db.find_device_by_guid(machine_guid)
    if not device or not device.get("email"):
        return {"role": None, "assigned_user": None}
    user = await neon_db.find_user_by_email(device["email"])
    if not user:
        return {"role": None, "assigned_user": None}
    return {"role": user.get("role", "employee"), "assigned_user": user["full_name"]}


# ---------------------------------------------------------------------------
# Admin setup (SQLite)
# ---------------------------------------------------------------------------

@app.post("/api/v1/admin/setup", response_model=MessageResponse, tags=["admin"])
def admin_setup(payload: dict) -> MessageResponse:
    email = payload.get("email", "").lower().strip()
    if email not in ALLOWED_ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Unauthorized email.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("admin_email", email),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="Admin verified and setup complete.")


@app.get("/api/v1/admin/status", response_model=dict, tags=["admin"])
def get_admin_status() -> dict:
    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute("SELECT value FROM settings WHERE key = 'admin_email'").fetchone()
    conn.close()
    return {"is_setup": row is not None, "admin_email": row["value"] if row else None}


# ---------------------------------------------------------------------------
# Settings (SQLite)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data ingestion — Events & Idle
# ---------------------------------------------------------------------------

@app.post("/api/v1/events", response_model=MessageResponse)
async def ingest_event(event: EventIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    if event.ended_at <= event.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")
    await neon_db.insert_event({
        "device_id": device_id,
        "started_at": parse_local_time(event.started_at),
        "ended_at": parse_local_time(event.ended_at),
        "app_name": event.app_name,
        "window_title": event.window_title,
        "url": event.url,
        "category": event.category,
        "productivity_label": event.productivity_label,
        "notes": event.notes,
        "source": event.source,
    })
    return MessageResponse(message="event ingested")


@app.post("/api/v1/idle", response_model=MessageResponse)
async def ingest_idle_period(period: IdlePeriodIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    if period.ended_at <= period.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")
    await neon_db.insert_idle_period({
        "device_id": device_id,
        "started_at": parse_local_time(period.started_at),
        "ended_at": parse_local_time(period.ended_at),
        "reason": period.reason,
    })
    return MessageResponse(message="idle period ingested")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/v1/dashboard/today", response_model=DashboardResponse)
async def dashboard_today(device_id: str | None = Query(None)) -> DashboardResponse:
    return await dashboard(date.today(), device_id)


@app.get("/api/v1/dashboard/{day}", response_model=DashboardResponse)
async def dashboard(day: date, device_id: str | None = Query(None)) -> DashboardResponse:
    cache_key = f"dashboard:{day}:{device_id}"
    ttl = 10 if day == date.today() else 86400
    cached = cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    try:
        day_events = [dict(r) for r in await neon_db.fetch_events(day, device_id)]
        day_idle   = [dict(r) for r in await neon_db.fetch_idle(day, device_id)]
        idle_seconds = sum(clamp_duration_seconds(r["started_at"], r["ended_at"]) for r in day_idle)
        result = DashboardResponse(
            day=day,
            kpis=build_kpis(day_events, idle_seconds),
            top_apps=build_top_app_items(day_events),
            timeline=build_timeline(day_events, day_idle),
            productivity_breakdown=build_productivity_breakdown(day_events, idle_seconds),
            summary=summarize_day(day_events, idle_seconds),
        )
        cache_set(cache_key, result)
        return result
    except Exception as exc:
        print(f"Dashboard error for {day}: {exc}")
        return DashboardResponse(
            day=day,
            kpis=build_kpis([], 0),
            top_apps=[],
            timeline=[],
            productivity_breakdown={"productive": 0, "neutral": 0, "distracting": 0, "idle": 0},
            summary="No tracked activity for this day yet.",
        )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.get("/api/v1/history/{day}", response_model=HistoryResponse)
async def history(day: date, device_id: str | None = Query(None)) -> HistoryResponse:
    day_events = [dict(r) for r in await neon_db.fetch_events(day, device_id)]
    day_idle   = [dict(r) for r in await neon_db.fetch_idle(day, device_id)]
    idle_seconds = sum(clamp_duration_seconds(r["started_at"], r["ended_at"]) for r in day_idle)
    return HistoryResponse(
        day=day,
        sessions=build_sessions(day_events),
        day_summary=summarize_day(day_events, idle_seconds),
    )


# ---------------------------------------------------------------------------
# Events list
# ---------------------------------------------------------------------------

@app.get("/api/v1/events", response_model=list[EventIn])
async def list_events(
    day: Annotated[date | None, Query(description="Optional date filter YYYY-MM-DD")] = None,
) -> list[EventIn]:
    rows = await neon_db.fetch_events_list(day)
    return [
        EventIn(
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            app_name=r["app_name"],
            window_title=r.get("window_title"),
            url=r.get("url"),
            category=r.get("category"),
            productivity_label=r.get("productivity_label") or "neutral",
            notes=r.get("notes"),
            source=r.get("source") or "agent",
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Editor context
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/editor", response_model=MessageResponse, tags=["editor"])
async def post_editor_context(payload: EditorContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    try:
        doc = payload.model_dump()
        doc["device_id"] = device_id
        doc["captured_at"] = parse_local_time(doc["captured_at"])
        await neon_db.insert_editor_context(doc)
        print(f"[EDITOR] stored: {doc['captured_at']} file={doc.get('active_file')} dev={device_id}")
        return MessageResponse(message="ok")
    except Exception as e:
        print(f"[EDITOR ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/context/editor/{day}", response_model=list[EditorContextItem], tags=["editor"])
async def get_editor_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(10000, le=20000),
) -> list[EditorContextItem]:
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    if not since and target != date.today():
        cache_key = f"editor:{day}:{device_id}:{limit}"
        cached = cache_get(cache_key, 86400)
        if cached is not None:
            return cached

    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            pass

    try:
        rows = await neon_db.query_context("editor_context", target, device_id, since_dt, limit)
        print(f"[GET editor] day={day} since={since} device={device_id} -> {len(rows)} rows")
        items = []
        for i, r in enumerate(rows):
            try:
                items.append(EditorContextItem(
                    id=i,
                    captured_at=r["captured_at"].strftime("%Y-%m-%dT%H:%M:%S"),
                    editor_app=r["editor_app"] or "Unknown",
                    workspace=r["workspace"],
                    active_file=r["active_file"],
                    active_file_path=r["active_file_path"],
                    language=r["language"],
                    open_files=list(r["open_files"] or []),
                    terminal_count=r["terminal_count"] or 0,
                    git_branch=r["git_branch"],
                    debugger_active=bool(r["debugger_active"]),
                ))
            except Exception as e:
                print(f"Error parsing editor context row: {e}")
        if not since and target != date.today():
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching editor context for {day}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/browser", response_model=MessageResponse, tags=["browser"])
async def post_browser_context(payload: BrowserContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    try:
        from app.services.classifier import classifier as _clf
        doc = payload.model_dump()
        doc["device_id"] = device_id
        doc["captured_at"] = parse_local_time(doc["captured_at"])
        doc["productivity_label"] = _clf.classify(doc.get("active_tab_title", ""), doc.get("active_tab_domain", ""))
        await neon_db.insert_browser_context(doc)
        print(f"[BROWSER] stored: {doc['captured_at']} domain={doc.get('active_tab_domain')} dev={device_id}")
        return MessageResponse(message="ok")
    except Exception as e:
        print(f"[BROWSER ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/context/browser/{day}", response_model=list[BrowserContextItem], tags=["browser"])
async def get_browser_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(10000, le=20000),
) -> list[BrowserContextItem]:
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    if not since and target != date.today():
        cache_key = f"browser:{day}:{device_id}:{limit}"
        cached = cache_get(cache_key, 86400)
        if cached is not None:
            return cached

    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            pass

    try:
        rows = await neon_db.query_context("browser_context", target, device_id, since_dt, limit)
        print(f"[GET browser] day={day} since={since} device={device_id} -> {len(rows)} rows")
        items = []
        for i, r in enumerate(rows):
            try:
                items.append(BrowserContextItem(
                    id=i,
                    captured_at=r["captured_at"].strftime("%Y-%m-%dT%H:%M:%S"),
                    browser_app=r["browser_app"] or "Unknown",
                    active_tab_url=r["active_tab_url"],
                    active_tab_title=r["active_tab_title"],
                    active_tab_domain=r["active_tab_domain"],
                    tab_count=r["tab_count"] or 0,
                    open_domains=list(r["open_domains"] or []),
                    youtube_video_title=r["youtube_video_title"],
                    youtube_channel=r["youtube_channel"],
                    youtube_is_playing=r["youtube_is_playing"],
                    youtube_progress_pct=r["youtube_progress_pct"],
                    productivity_label=r["productivity_label"] or "neutral",
                ))
            except Exception as e:
                print(f"Error parsing browser context row: {e}")
        if not since and target != date.today():
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching browser context for {day}: {exc}")
        return []


# ---------------------------------------------------------------------------
# App context
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/app", response_model=MessageResponse, tags=["app"])
async def post_app_context(payload: AppContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    doc = payload.model_dump()
    doc["device_id"] = device_id
    doc["captured_at"] = parse_local_time(doc["captured_at"])
    await neon_db.insert_app_context(doc)
    return MessageResponse(message="ok")


@app.get("/api/v1/context/app/{day}", response_model=list[AppContextItem], tags=["app"])
async def get_app_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(10000, le=20000),
) -> list[AppContextItem]:
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    if not since and target != date.today():
        cache_key = f"app:{day}:{device_id}:{limit}"
        cached = cache_get(cache_key, 86400)
        if cached is not None:
            return cached

    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            pass

    try:
        rows = await neon_db.query_context("app_context", target, device_id, since_dt, limit)
        items = []
        for i, r in enumerate(rows):
            try:
                items.append(AppContextItem(
                    id=i,
                    captured_at=r["captured_at"].strftime("%Y-%m-%dT%H:%M:%S"),
                    app_name=r["app_name"] or "Unknown",
                    active_file_name=r["active_file_name"],
                    active_file_path=r["active_file_path"],
                    active_sequence=r["active_sequence"],
                    notes=r["notes"],
                ))
            except Exception as e:
                print(f"Error parsing app context row: {e}")
        if not since and target != date.today():
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching app context for {day}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Frontend fallback (must be last)
# ---------------------------------------------------------------------------
if static_dir.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "Frontend not found"}


# ---------------------------------------------------------------------------
# Entry point for PyInstaller EXE
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting TrackFlow Server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
