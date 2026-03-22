from __future__ import annotations

import os
import sys
from datetime import date, datetime
from typing import Annotated

# Fix stdout/stderr for PyInstaller --noconsole mode (Windows sets them to None)
if getattr(sys, "frozen", False) and sys.stdout is None:
    from pathlib import Path as _P
    _log_path = _P(os.getenv("APPDATA", _P.home() / "AppData/Roaming")) / "TrackFlow" / "server.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
    sys.stdout = _log_file
    sys.stderr = _log_file

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import json as _json
from pathlib import Path
from contextlib import asynccontextmanager

from app.db import get_connection, init_db
from app.mongo_db import mongodb
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
from fastapi import Header
import uuid as uuid_pkg
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

ALLOWED_ADMIN_EMAILS = [
    "kushagra.vyas@varaheanalytics.com",
    "raj.sharma@varaheanalytics.com",
    "nitin.by@varaheanalytics.com"
]

APP_NAME = os.getenv("APP_NAME", "TrackFlow")

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache for read-heavy endpoints
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
    """Return (start, end) as naive datetimes for a given date."""
    return datetime.combine(day, datetime.min.time()), datetime.combine(day, datetime.max.time())

def parse_local_time(val) -> datetime:
    """Parse a local time string or datetime to a naive datetime.
    Extensions now send local time without timezone suffix (e.g. '2026-03-18T17:15:18').
    If it still has a Z or offset, convert to local and strip tzinfo."""
    if isinstance(val, str):
        val = val.replace('Z', '+00:00') if 'Z' in val else val
        val = datetime.fromisoformat(val)
    if not isinstance(val, datetime):
        return val
    if val.tzinfo is not None:
        val = val.astimezone()  # to system local
        val = val.replace(tzinfo=None)
    return val

def device_filter(device_id: str | None) -> dict:
    """Build a MongoDB filter for device_id. Legacy data is normalized at startup."""
    if device_id is None:
        return {}
    return {"device_id": device_id}
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]

async def _normalize_device_ids():
    """One-time migration: copy machine_guid into device_id for legacy records."""
    collections = ["events", "idle_periods", "editor_context", "browser_context", "app_context"]
    for coll_name in collections:
        coll = mongodb.db[coll_name]
        # Records where device_id is null but machine_guid exists
        res1 = await coll.update_many(
            {"device_id": None, "machine_guid": {"$exists": True, "$ne": None}},
            [{"$set": {"device_id": "$machine_guid"}}]
        )
        # Records where device_id field doesn't exist but machine_guid does
        res2 = await coll.update_many(
            {"device_id": {"$exists": False}, "machine_guid": {"$exists": True, "$ne": None}},
            [{"$set": {"device_id": "$machine_guid"}}]
        )
        total = res1.modified_count + res2.modified_count
        if total > 0:
            print(f"Normalized {total} legacy records in {coll_name}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    # Initialize SQL for legacy/fallback if needed, but primarily MongoDB
    init_db()
    await mongodb.connect()
    await mongodb.ensure_indexes()
    await neon_db.init_neon()
    # Run migration in background — don't block server startup
    asyncio.get_event_loop().create_task(_normalize_device_ids())
    yield
    await neon_db.close_neon()
    await mongodb.close()

app = FastAPI(title="TrackFlow API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- Serve Frontend (Admin Dashboard) ---
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    static_dir = Path(sys._MEIPASS) / "static"
else:
    # Running in normal Python environment
    static_dir = Path(__file__).parent.parent / "static"

if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name=APP_NAME)


# --- Multi-User / Multi-Device Helpers & Endpoints ---

async def get_device_id(machine_guid: str | None = Header(None, alias="X-Machine-GUID")) -> str | None:
    return machine_guid


@app.post("/api/v1/admin/users", response_model=UserItem, tags=["admin"])
async def create_user(user: UserIn) -> UserItem:
    # Check for duplicate email first
    existing = await mongodb.db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=409, detail=f"User with email {user.email} already exists")

    token = str(uuid_pkg.uuid4())[:8].upper()
    new_user = {
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "registration_token": token,
        "created_at": datetime.now()
    }
    try:
        await mongodb.db.users.insert_one(new_user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Email already exists or error: {e}")
    
    return UserItem(
        id=0,
        full_name=new_user["full_name"],
        email=new_user["email"],
        role=new_user["role"],
        registration_token=new_user["registration_token"],
        created_at=new_user["created_at"]
    )


@app.delete("/api/v1/admin/users/{email}", response_model=MessageResponse, tags=["admin"])
async def delete_user(email: str) -> MessageResponse:
    result = await mongodb.db.users.delete_one({"email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} deleted successfully")


@app.put("/api/v1/admin/users/{email}/role", response_model=MessageResponse, tags=["admin"])
async def update_user_role(email: str, payload: UserRoleUpdateIn) -> MessageResponse:
    result = await mongodb.db.users.update_one(
        {"email": email},
        {"$set": {"role": payload.role}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} role updated to {payload.role}")


@app.put("/api/v1/admin/users/{email}", response_model=MessageResponse, tags=["admin"])
async def update_user(email: str, payload: UserUpdateIn) -> MessageResponse:
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        return MessageResponse(message="No changes provided")
    
    result = await mongodb.db.users.update_one(
        {"email": email},
        {"$set": update_data}
    )
    
    # Also update email in devices if it changed
    if "email" in update_data and update_data["email"] != email:
         await mongodb.db.devices.update_many(
             {"email": email},
             {"$set": {"email": update_data["email"]}}
         )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return MessageResponse(message=f"User {email} updated successfully")


@app.post("/api/v1/admin/devices/{machine_guid}/assign", response_model=MessageResponse, tags=["admin"])
async def assign_device(machine_guid: str, payload: DeviceAssignIn) -> MessageResponse:
    # 1. Upsert the User
    token = str(uuid_pkg.uuid4())[:8].upper()
    user_update = {
        "full_name": payload.full_name,
        "email": payload.email,
        "role": payload.role,
    }
    
    # We use find_one_and_update to ensure we don't overwrite reg token if user exists
    user = await mongodb.db.users.find_one_and_update(
        {"email": payload.email},
        {"$set": user_update, "$setOnInsert": {"registration_token": token, "created_at": datetime.now()}},
        upsert=True,
        return_document=True
    )

    # 2. Update Device to point to this user
    result = await mongodb.db.devices.update_one(
        {"machine_guid": machine_guid},
        {"$set": {"email": payload.email, "last_seen_at": datetime.now()}},
        upsert=True
    )
    
    return MessageResponse(message=f"Device {machine_guid[:8]} assigned to {payload.email}")


@app.post("/api/v1/admin/setup", response_model=MessageResponse, tags=["admin"])
def admin_setup(payload: dict) -> MessageResponse:
    """Verify admin email and lock the system to that admin."""
    email = payload.get("email", "").lower().strip()
    if email not in ALLOWED_ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Unauthorized email. This machine is not authorized for Admin Setup.")
    
    conn = get_connection()
    cur = conn.cursor()
    # Store verified admin email in settings
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("admin_email", email),
    )
    conn.commit()
    conn.close()
    return MessageResponse(message="Admin verified and setup complete.")


@app.get("/api/v1/admin/status", response_model=dict, tags=["admin"])
def get_admin_status() -> dict:
    """Check if admin is already set up."""
    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute("SELECT value FROM settings WHERE key = 'admin_email'").fetchone()
    conn.close()
    return {"is_setup": row is not None, "admin_email": row["value"] if row else None}


@app.get("/api/v1/admin/users", response_model=list[UserItem], tags=["admin"])
async def list_users() -> list[UserItem]:
    cursor = mongodb.db.users.find({})
    rows = await cursor.to_list(length=1000)
    return [
        UserItem(
            id=0,
            full_name=r["full_name"],
            email=r["email"],
            role=r.get("role", "employee"),
            registration_token=r["registration_token"],
            created_at=r["created_at"] if isinstance(r["created_at"], datetime) else datetime.fromisoformat(r["created_at"])
        ) for r in rows
    ]


@app.post("/api/v1/register", response_model=RegisterResponse, tags=["registration"])
async def register_device(reg: DeviceRegisterIn) -> RegisterResponse:
    # 1. Check if device exists
    device = await mongodb.db.devices.find_one({"machine_guid": reg.machine_guid})

    # 2. If token is provided, link to existing user
    if reg.registration_token:
        user = await mongodb.db.users.find_one({"registration_token": reg.registration_token})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid registration token")

        await mongodb.db.devices.update_one(
            {"machine_guid": reg.machine_guid},
            {
                "$set": {
                    "email": user["email"],
                    "os_type": reg.os_type,
                    "last_seen_at": datetime.now()
                },
                "$setOnInsert": {"registered_at": datetime.now()}
            },
            upsert=True
        )
        device = await mongodb.db.devices.find_one({"machine_guid": reg.machine_guid})

    # 3. If name/email provided (tokenless registration), auto-create user and link device
    elif reg.full_name and reg.email:
        token = str(uuid_pkg.uuid4())[:8].upper()
        await mongodb.db.users.update_one(
            {"email": reg.email},
            {
                "$set": {"full_name": reg.full_name},
                "$setOnInsert": {
                    "role": "employee",
                    "registration_token": token,
                    "created_at": datetime.now()
                }
            },
            upsert=True
        )
        await mongodb.db.devices.update_one(
            {"machine_guid": reg.machine_guid},
            {
                "$set": {
                    "email": reg.email,
                    "os_type": reg.os_type,
                    "last_seen_at": datetime.now()
                },
                "$setOnInsert": {"registered_at": datetime.now()}
            },
            upsert=True
        )
        device = await mongodb.db.devices.find_one({"machine_guid": reg.machine_guid})

    # 4. Otherwise just register the device (unassigned)
    else:
        await mongodb.db.devices.update_one(
            {"machine_guid": reg.machine_guid},
            {
                "$set": {"os_type": reg.os_type, "last_seen_at": datetime.now()},
                "$setOnInsert": {"registered_at": datetime.now()}
            },
            upsert=True
        )

    # 5. Prepare response — ALWAYS include mongodb_uri so agent can write data
    resp = RegisterResponse(message="Device reported.")
    resp.mongodb_uri = os.getenv("MONGODB_URI")
    resp.mongodb_db = os.getenv("MONGODB_DB", "tracker")

    # If device is assigned to an email, add user details
    if device:
        assigned_email = device.get("email")
    else:
        device = await mongodb.db.devices.find_one({"machine_guid": reg.machine_guid})
        assigned_email = device.get("email") if device else None

    if assigned_email:
        user = await mongodb.db.users.find_one({"email": assigned_email})
        if user:
            resp.assigned_user = user["full_name"]
            resp.role = user.get("role", "employee")
            resp.message = "Device registered and assigned."

    return resp


@app.get("/api/v1/admin/devices", response_model=list[DeviceItem], tags=["admin"])
async def list_devices() -> list[DeviceItem]:
    cursor = mongodb.db.devices.find({})
    rows = await cursor.to_list(length=1000)
    return [
        DeviceItem(
            id=0,
            machine_guid=r["machine_guid"],
            os_type=r.get("os_type"),
            user_id=r.get("user_id"),
            email=r.get("email"),
            registered_at=r["registered_at"] if isinstance(r["registered_at"], datetime) else datetime.fromisoformat(r["registered_at"]),
            last_seen_at=r.get("last_seen_at") if (not r.get("last_seen_at") or isinstance(r.get("last_seen_at"), datetime)) else datetime.fromisoformat(r["last_seen_at"])
        ) for r in rows
    ]


# --- Data Ingestion Endpoints (Updated) ---


@app.post("/api/v1/events", response_model=MessageResponse)
async def ingest_event(event: EventIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    if event.ended_at <= event.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    new_event = {
        "device_id": device_id,
        "started_at": parse_local_time(event.started_at),
        "ended_at": parse_local_time(event.ended_at),
        "app_name": event.app_name,
        "window_title": event.window_title,
        "url": event.url,
        "category": event.category,
        "productivity_label": event.productivity_label,
        "notes": event.notes,
        "source": event.source
    }
    await mongodb.db.events.insert_one(new_event)
    return MessageResponse(message="event ingested")


@app.post("/api/v1/idle", response_model=MessageResponse)
async def ingest_idle_period(period: IdlePeriodIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    if period.ended_at <= period.started_at:
        raise HTTPException(status_code=400, detail="ended_at must be after started_at")

    new_idle = {
        "device_id": device_id,
        "started_at": parse_local_time(period.started_at),
        "ended_at": parse_local_time(period.ended_at),
        "reason": period.reason
    }
    await mongodb.db.idle_periods.insert_one(new_idle)
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
async def dashboard_today(device_id: str | None = Query(None)) -> DashboardResponse:
    return await dashboard(date.today(), device_id)


@app.get("/api/v1/dashboard/{day}", response_model=DashboardResponse)
async def dashboard(day: date, device_id: str | None = Query(None)) -> DashboardResponse:
    # Cache: past days are immutable (24h TTL), today refreshes every 10s
    cache_key = f"dashboard:{day}:{device_id}"
    ttl = 10 if day == date.today() else 86400
    cached = cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    start_dt, end_dt = naive_day_range(day)

    query: dict = {"started_at": {"$gte": start_dt, "$lte": end_dt}}
    query.update(device_filter(device_id))

    try:
        cursor_events = mongodb.db.events.find(query).sort("started_at", 1)
        day_events = await cursor_events.to_list(length=5000)

        cursor_idle = mongodb.db.idle_periods.find(query).sort("started_at", 1)
        day_idle = await cursor_idle.to_list(length=1000)

        idle_seconds = sum(
            clamp_duration_seconds(row["started_at"], row["ended_at"])
            for row in day_idle
        )

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


@app.get("/api/v1/history/{day}", response_model=HistoryResponse)
async def history(day: date, device_id: str | None = Query(None)) -> HistoryResponse:
    start_dt, end_dt = naive_day_range(day)
    
    query: dict = {"started_at": {"$gte": start_dt, "$lte": end_dt}}
    query.update(device_filter(device_id))
        
    cursor_events = mongodb.db.events.find(query).sort("started_at", 1)
    day_events = await cursor_events.to_list(length=5000)
    
    cursor_idle = mongodb.db.idle_periods.find(query).sort("started_at", 1)
    day_idle = await cursor_idle.to_list(length=1000)

    idle_seconds = sum(
        clamp_duration_seconds(row["started_at"], row["ended_at"])
        for row in day_idle
    )

    return HistoryResponse(
        day=day,
        sessions=build_sessions(day_events),
        day_summary=summarize_day(day_events, idle_seconds),
    )


@app.get("/api/v1/events", response_model=list[EventIn])
async def list_events(
    day: Annotated[date | None, Query(description="Optional date filter in YYYY-MM-DD")] = None,
) -> list[EventIn]:
    query = {}
    if day:
        start_dt = datetime.combine(day, datetime.min.time())
        end_dt = datetime.combine(day, datetime.max.time())
        query["started_at"] = {"$gte": start_dt, "$lte": end_dt}
        
    cursor = mongodb.db.events.find(query).sort("started_at", 1)
    rows = await cursor.to_list(length=5000)

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
# Editor context endpoints  (data from VS Code / Antigravity extension)
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/editor", response_model=MessageResponse, tags=["editor"])
async def post_editor_context(payload: EditorContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    """Receive an editor context snapshot (files, git, etc.) from VS Code."""
    doc = payload.model_dump()
    doc["device_id"] = device_id
    doc["machine_guid"] = device_id
    doc["captured_at"] = parse_local_time(doc["captured_at"])
    await neon_db.insert_editor_context(doc)
    return MessageResponse(message="ok")


@app.get("/api/v1/context/editor/{day}", response_model=list[EditorContextItem], tags=["editor"])
async def get_editor_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(500, le=5000),
) -> list[EditorContextItem]:
    """Return editor context snapshots for a given day (YYYY-MM-DD).
    Pass ?since=ISO_TIMESTAMP to get only newer records (incremental fetch)."""
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    # Cache (skip if incremental fetch)
    if not since:
        cache_key = f"editor:{day}:{device_id}:{limit}"
        ttl = 10 if target == date.today() else 86400
        cached = cache_get(cache_key, ttl)
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
                continue
        if not since:
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching editor context for {day}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Browser context endpoints  (data from Chrome / Brave extension)
# ---------------------------------------------------------------------------

@app.post("/api/v1/context/browser", response_model=MessageResponse, tags=["browser"])
async def post_browser_context(payload: BrowserContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    """Receive a browser context snapshot (tabs, YouTube, etc.) from extension."""
    from app.services.classifier import classifier as _browser_classifier
    doc = payload.model_dump()
    doc["device_id"] = device_id
    doc["machine_guid"] = device_id
    doc["captured_at"] = parse_local_time(doc["captured_at"])
    doc["productivity_label"] = _browser_classifier.classify(
        doc.get("active_tab_title", ""),
        doc.get("active_tab_domain", "")
    )
    await neon_db.insert_browser_context(doc)
    return MessageResponse(message="ok")


@app.get("/api/v1/context/browser/{day}", response_model=list[BrowserContextItem], tags=["browser"])
async def get_browser_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(500, le=5000),
) -> list[BrowserContextItem]:
    """Return browser context snapshots for a given day (YYYY-MM-DD).
    Pass ?since=ISO_TIMESTAMP to get only newer records (incremental fetch)."""
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    # Cache (skip if incremental fetch)
    if not since:
        cache_key = f"browser:{day}:{device_id}:{limit}"
        ttl = 10 if target == date.today() else 86400
        cached = cache_get(cache_key, ttl)
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
                continue
        if not since:
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching browser context for {day}: {exc}")
        return []

@app.post("/api/v1/context/app", response_model=MessageResponse, tags=["app"])
async def post_app_context(payload: AppContextIn, device_id: str | None = Depends(get_device_id)) -> MessageResponse:
    """Receive a generic application context snapshot (Adobe, DaVinci, etc.)."""
    doc = payload.model_dump()
    doc["device_id"] = device_id
    doc["machine_guid"] = device_id
    doc["captured_at"] = parse_local_time(doc["captured_at"])
    await neon_db.insert_app_context(doc)
    return MessageResponse(message="ok")
@app.get("/api/v1/context/app/{day}", response_model=list[AppContextItem], tags=["app"])
async def get_app_context(
    day: str,
    device_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(500, le=5000),
) -> list[AppContextItem]:
    """Return application context snapshots for a given day (YYYY-MM-DD).
    Pass ?since=ISO_TIMESTAMP to get only newer records (incremental fetch)."""
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    # Cache (skip if incremental fetch)
    if not since:
        cache_key = f"app:{day}:{device_id}:{limit}"
        ttl = 10 if target == date.today() else 86400
        cached = cache_get(cache_key, ttl)
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
                continue
        if not since:
            cache_set(cache_key, items)
        return items
    except Exception as exc:
        print(f"Error fetching app context for {day}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Frontend Fallback Route (Must be last to not intercept API calls)
# ---------------------------------------------------------------------------
if static_dir.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # Allow /api and /docs and /openapi.json to pass through
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        
        # Fallback to index.html for React Router
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "Frontend not found"}


# ---------------------------------------------------------------------------
# Entry point for PyInstaller EXE (starts uvicorn server)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting TrackFlow Server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
